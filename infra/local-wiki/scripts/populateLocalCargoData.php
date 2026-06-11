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
		// Parallelism: run N copies of this script, one per --shard; the
		// block-dealing note in execute() explains how work is split.
		$this->addOption( 'shards', 'Total number of parallel workers', false, true );
		$this->addOption( 'shard', '0-based index of this worker', false, true );
		// Manual escape hatch: re-store a single page (debugging, or after a
		// page failed all its retries in a parallel run).
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
			$pageIDs = $this->findPagesThatCanStore( $dbr );
		}
		if ( $this->hasOption( 'shard' ) && !$this->hasOption( 'shards' ) ) {
			$this->fatalError( '--shard requires --shards' );
		}
		$shards = max( 1, (int)$this->getOption( 'shards', 1 ) );
		$shard = (int)$this->getOption( 'shard', 0 );
		if ( $shards > 1 ) {
			// Deal BLOCKS of adjacent page-ids round-robin. Primary goal is
			// load balance: expensive same-kind clusters (game pages, player
			// profiles) spread across all workers instead of serializing in
			// whichever worker got a contiguous slice. The block granularity
			// also reduces interleaving on the tables the advisory lock
			// below does NOT cover (1-2-row stores like profiles), where the
			// retry loop handles the residual races.
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
			// the retry below absorbs the rare clash. Game titles share the
			// "<sport prefix:>dd-dd-dddd" shape across all sports (football
			// uses the משחק: prefix), so the lock key is derived rather than
			// enumerated — a future sport is covered automatically.
			$lockKey = null;
			if ( preg_match( '/^(?:([^:]+):\s?)?\d{2}-\d{2}-\d{4} /u', $prefixedTitle, $match ) && !empty( $match[1] ) ) {
				$lockKey = 'cargo-populate-games-' . $match[1];
			}
			if ( $lockKey !== null && !$dbw->lock( $lockKey, __METHOD__, 120 ) ) {
				// Timed out waiting — proceed unprotected; the retry loop
				// below still absorbs a collision.
				$this->output( "$label [$processed/$total] $prefixedTitle — WARNING: lock '$lockKey' timed out\n" );
				$lockKey = null;
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
					if ( $attempts >= 5 ) {
						$failed++;
						$this->output( "$label [$processed/$total] $prefixedTitle — ERROR after $attempts attempts: "
							. $exception->getMessage() . "\n" );
						break;
					}
					// Jitter so two workers that just collided on the same
					// table don't immediately collide again.
					usleep( random_int( 200000, 1000000 ) * $attempts );
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

	/**
	 * Only pages whose parse can reach a #cargo_store call need a save
	 * replay: pages whose own wikitext contains one, plus pages that
	 * transclude a template that does. Everything else (~60% of the wiki)
	 * provably stores nothing — skipping them more than halves the run.
	 * Requires the link tables to be rebuilt first (seed-content.sh does).
	 */
	private function findPagesThatCanStore( $dbr ) {
		$page = $dbr->tableName( 'page' );
		$revision = $dbr->tableName( 'revision' );
		$slots = $dbr->tableName( 'slots' );
		$content = $dbr->tableName( 'content' );
		$text = $dbr->tableName( 'text' );

		// Pages whose latest revision text mentions cargo_store. The LIKE is
		// permissive (docs mentioning it match too) — false positives just
		// cost one parse that stores nothing.
		$storePages = [];
		$storeTemplateTitles = [];
		$result = $dbr->query(
			"SELECT p.page_id, p.page_namespace, p.page_title
			FROM $page p
			JOIN $revision r ON r.rev_page = p.page_id AND p.page_latest = r.rev_id
			JOIN $slots s ON s.slot_revision_id = r.rev_id
			JOIN $content c ON c.content_id = s.slot_content_id
			JOIN $text t ON t.old_id = CAST(SUBSTRING(c.content_address, 4) AS UNSIGNED)
			WHERE p.page_is_redirect = 0 AND t.old_text LIKE '%cargo_store%'",
			__METHOD__
		);
		foreach ( $result as $row ) {
			$storePages[] = (int)$row->page_id;
			if ( (int)$row->page_namespace === NS_TEMPLATE ) {
				$storeTemplateTitles[] = $row->page_title;
			}
		}
		if ( !$storePages ) {
			// Either no store-bearing templates are imported yet, or the
			// raw-SQL text-table assumptions above (tt: addresses, plain
			// utf-8 text) no longer hold — don't "succeed" with empty tables.
			$this->fatalError( 'no page contains #cargo_store — import the templates first,'
				. ' or check the text-storage assumptions in findPagesThatCanStore()' );
		}

		// Pages transcluding any store-bearing template (templatelinks is
		// flattened, so indirect transclusion through wrapper templates is
		// covered).
		$transcluders = [];
		if ( $storeTemplateTitles ) {
			$transcluders = $dbr->selectFieldValues(
				[ 'templatelinks', 'linktarget', 'page' ],
				'DISTINCT tl_from',
				[
					'lt_namespace' => NS_TEMPLATE,
					'lt_title' => $storeTemplateTitles,
					'page_is_redirect' => 0,
				],
				__METHOD__,
				[],
				[
					'linktarget' => [ 'JOIN', 'lt_id = tl_target_id' ],
					'page' => [ 'JOIN', 'page_id = tl_from' ],
				]
			);
		}

		$pageIDs = array_map( 'intval', array_unique( array_merge( $storePages, $transcluders ) ) );
		sort( $pageIDs );
		return $pageIDs;
	}

}

require_once RUN_MAINTENANCE_IF_MAIN;
