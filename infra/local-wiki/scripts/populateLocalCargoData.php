<?php

/**
 * Populate the local Cargo tables by re-parsing every page with the same
 * store semantics as a real page save.
 *
 * Why this exists: on MaccabiPedia most #cargo_store calls live in content
 * templates (e.g. תבנית:קטלוג משחקים) that neither declare nor #cargo_attach
 * to their tables, so Cargo's own cargoRecreateData.php — which only re-parses
 * pages transcluding the declaring/attached templates — finds nothing to do.
 * On prod the rows land at page-save time instead. Locally, pages arrive via
 * importDump.php which never fires the save hooks, so after creating the
 * tables (scripts/recreate-cargo-tables.sh) this script replays the
 * page-save store for every page.
 *
 * Runs inside the mediawiki container, copied next to core's maintenance
 * scripts by recreate-cargo-tables.sh:
 *   php maintenance/populateLocalCargoData.php
 *
 * Idempotent: each page's previous Cargo rows are deleted (the same cleanup
 * a real save performs) before its #cargo_store calls run again.
 */

if ( getenv( 'MW_INSTALL_PATH' ) ) {
	require_once getenv( 'MW_INSTALL_PATH' ) . '/maintenance/Maintenance.php';
} else {
	require_once __DIR__ . '/Maintenance.php';
}

use MediaWiki\MediaWikiServices;

$maintClass = PopulateLocalCargoData::class;

class PopulateLocalCargoData extends Maintenance {

	public function __construct() {
		parent::__construct();
		$this->requireExtension( 'Cargo' );
		$this->addDescription( 'Re-store Cargo data for every page, as if each page were re-saved.' );
		// Parallelism: run N copies of this script, one per shard. Each shard
		// takes a CONTIGUOUS slice of the page-id space — imported pages of
		// the same kind have adjacent ids, so concurrent workers mostly write
		// to different Cargo tables. That matters because Cargo allocates row
		// ids with an unlocked MAX(_ID)+1 (_ID is the PK), so two workers
		// storing into the same table can collide; the per-page retry below
		// absorbs the rare cross-shard collision.
		$this->addOption( 'shards', 'Total number of parallel workers', false, true );
		$this->addOption( 'shard', '0-based index of this worker', false, true );
		// Escape hatch for pages that lost the race in a parallel run.
		$this->addOption( 'title', 'Re-store only this page', false, true );
	}

	public function execute() {
		$wikiPageFactory = MediaWikiServices::getInstance()->getWikiPageFactory();
		$dbr = $this->getDB( DB_REPLICA );
		$dbw = $this->getDB( DB_PRIMARY );
		if ( $this->hasOption( 'title' ) ) {
			$onlyTitle = Title::newFromText( $this->getOption( 'title' ) );
			if ( $onlyTitle == null || !$onlyTitle->exists() ) {
				$this->fatalError( 'page not found: ' . $this->getOption( 'title' ) );
			}
			$pageIDs = [ $onlyTitle->getArticleID() ];
		} else {
			$pageIDs = $dbr->selectFieldValues(
				'page',
				'page_id',
				[ 'page_is_redirect' => 0 ],
				__METHOD__,
				[ 'ORDER BY' => 'page_id' ]
			);
		}
		$shards = max( 1, (int)$this->getOption( 'shards', 1 ) );
		$shard = (int)$this->getOption( 'shard', 0 );
		if ( $shards > 1 ) {
			// Deal BLOCKS of adjacent page-ids round-robin: blocks keep
			// same-kind pages (which store into the same tables) mostly
			// within one worker — limiting MAX(_ID)+1 races — while the
			// round-robin spreads expensive page clusters (e.g. player
			// profiles) across all workers instead of serializing them
			// in whichever worker got that contiguous slice.
			$mine = [];
			foreach ( array_chunk( $pageIDs, 32 ) as $blockIndex => $block ) {
				if ( $blockIndex % $shards === $shard ) {
					$mine = array_merge( $mine, $block );
				}
			}
			$pageIDs = $mine;
		}
		$label = $shards > 1 ? "[w$shard]" : '';
		$total = count( $pageIDs );
		$this->output( "$label $total pages to process.\n" );

		$processed = 0;
		$failed = 0;
		foreach ( $pageIDs as $pageID ) {
			$processed++;
			$title = Title::newFromID( $pageID );
			if ( $title == null ) {
				$this->output( "$label [$processed/$total] page id $pageID — SKIP: no title\n" );
				continue;
			}
			$prefixedTitle = $title->getPrefixedText();
			$wikiPage = $wikiPageFactory->newFromID( $pageID );
			if ( $wikiPage == null ) {
				$this->output( "$label [$processed/$total] $prefixedTitle — SKIP: no wiki page\n" );
				continue;
			}
			$content = $wikiPage->getContent();
			if ( $content == null ) {
				$this->output( "$label [$processed/$total] $prefixedTitle — SKIP: no content\n" );
				continue;
			}
			$contentText = ContentHandler::getContentText( $content );

			// Game pages store dozens of per-event rows, each allocated via
			// Cargo's unlocked MAX(_ID)+1 — two workers on same-sport game
			// pages collide near-certainly. Serialize ONLY those through a
			// per-sport advisory lock; everything else stores 1-2 rows and
			// the retry below absorbs the rare clash.
			$lockKey = null;
			if ( strpos( $prefixedTitle, 'משחק:' ) === 0 ) {
				$lockKey = 'cargo-populate-football-games';
			} elseif ( preg_match( '/^כדורסל:\d{2}-/u', $prefixedTitle ) ) {
				$lockKey = 'cargo-populate-basketball-games';
			} elseif ( preg_match( '/^כדורעף:\d{2}-/u', $prefixedTitle ) ) {
				$lockKey = 'cargo-populate-volleyball-games';
			}
			if ( $lockKey !== null ) {
				$dbw->lock( $lockKey, __METHOD__, 120 );
			}

			// Same sequence as CargoHooks::onPageSaveComplete: drop the
			// page's old rows, then re-parse so #cargo_store re-adds them.
			// Retried because parallel workers can race on Cargo's
			// MAX(_ID)+1 row-id allocation; the delete makes a retry clean.
			$startTime = microtime( true );
			$attempts = 0;
			while ( true ) {
				$attempts++;
				try {
					CargoHooks::deletePageFromSystem( $pageID );
					CargoStore::$settings['origin'] = 'page save';
					CargoUtils::parsePageForStorage( $title, $contentText );
					break;
				} catch ( Throwable $exception ) {
					// A failed store can leave Cargo's DB connection with an
					// open explicit transaction; clear it, or this worker's
					// every later page fails with "explicit transaction
					// already active".
					try {
						CargoUtils::getDB()->rollback( __METHOD__ );
					} catch ( Throwable $rollbackError ) {
						// No open transaction to roll back — fine.
					}
					// Jitter so two workers that just collided on the same
					// table don't immediately collide again.
					usleep( random_int( 200000, 1000000 ) * $attempts );
					if ( $attempts >= 5 ) {
						$failed++;
						$this->output( "$label [$processed/$total] $prefixedTitle — ERROR after $attempts attempts: "
							. $exception->getMessage() . "\n" );
						break;
					}
					$this->output( "$label [$processed/$total] $prefixedTitle — retrying (attempt $attempts): "
						. $exception->getMessage() . "\n" );
				}
			}

			if ( $lockKey !== null ) {
				$dbw->unlock( $lockKey, __METHOD__ );
			}

			// cargo_pages records which tables this page just stored into.
			$storedTables = $dbw->selectFieldValues(
				'cargo_pages', 'table_name', [ 'page_id' => $pageID ], __METHOD__
			);
			$elapsedMs = (int)( ( microtime( true ) - $startTime ) * 1000 );
			$storedNote = $storedTables ? 'stored: ' . implode( ', ', $storedTables ) : 'no cargo data';
			$this->output( "$label [$processed/$total] $prefixedTitle — $storedNote (${elapsedMs}ms)\n" );
		}
		$this->output( "$label done — $processed pages processed, $failed failed.\n" );
		if ( $failed > 0 ) {
			$this->fatalError( "$label $failed page(s) failed to store" );
		}
	}

}

require_once RUN_MAINTENANCE_IF_MAIN;
