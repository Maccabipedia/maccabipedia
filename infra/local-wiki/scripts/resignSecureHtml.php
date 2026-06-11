<?php

/**
 * Re-sign <shtml> blocks with the LOCAL SecureHTML key.
 *
 * SecureHTML renders its raw-HTML payload only when the tag's hash attribute
 * equals hash_hmac(sha256, payload, $wgSecureHTMLSecrets[...]). Imported prod
 * pages carry hashes signed with PROD's secret (never in this repo), so every
 * <shtml> block renders "שגיאה:גיבוב (hash) לא חוקי" locally. This script
 * recomputes each block's hash with the local dev key and saves the page.
 *
 * Idempotent: blocks already signed with the local key are left untouched.
 * Runs inside the mediawiki container, copied next to core's maintenance
 * scripts by seed-content.sh:
 *   php maintenance/resignSecureHtml.php
 */

if ( getenv( 'MW_INSTALL_PATH' ) ) {
	require_once getenv( 'MW_INSTALL_PATH' ) . '/maintenance/Maintenance.php';
} else {
	require_once __DIR__ . '/Maintenance.php';
}

use MediaWiki\MediaWikiServices;

$maintClass = ResignSecureHtml::class;

class ResignSecureHtml extends Maintenance {

	public function __construct() {
		parent::__construct();
		$this->requireExtension( 'Secure HTML' );
		$this->addDescription( 'Re-sign <shtml> hashes with the local SecureHTML secret.' );
	}

	public function execute() {
		global $wgSecureHTMLTag, $wgSecureHTMLSecrets;

		if ( !$wgSecureHTMLSecrets ) {
			$this->fatalError( 'no $wgSecureHTMLSecrets configured' );
		}
		$secret = reset( $wgSecureHTMLSecrets );
		if ( is_array( $secret ) ) {
			$secret = $secret['secret'];
		}
		$tag = preg_quote( $wgSecureHTMLTag, '~' );

		$dbr = $this->getDB( DB_REPLICA );
		$page = $dbr->tableName( 'page' );
		$revision = $dbr->tableName( 'revision' );
		$slots = $dbr->tableName( 'slots' );
		$content = $dbr->tableName( 'content' );
		$text = $dbr->tableName( 'text' );
		$pageIDs = $dbr->query(
			"SELECT p.page_id
			FROM $page p
			JOIN $revision r ON r.rev_page = p.page_id AND p.page_latest = r.rev_id
			JOIN $slots s ON s.slot_revision_id = r.rev_id
			JOIN $content c ON c.content_id = s.slot_content_id
			JOIN $text t ON t.old_id = CAST(SUBSTRING(c.content_address, 4) AS UNSIGNED)
			WHERE t.old_text LIKE '%<{$wgSecureHTMLTag}%'",
			__METHOD__
		);

		$user = User::newSystemUser( 'Maintenance script', [ 'steal' => true ] );
		$wikiPageFactory = MediaWikiServices::getInstance()->getWikiPageFactory();
		$resigned = 0;
		$unchanged = 0;
		foreach ( $pageIDs as $row ) {
			$wikiPage = $wikiPageFactory->newFromID( (int)$row->page_id );
			if ( $wikiPage == null ) {
				continue;
			}
			$wikitext = ContentHandler::getContentText( $wikiPage->getContent() );

			// The parser hands SecureHTML the EXACT inner text between the
			// tags, so the HMAC here must run over the same byte-exact slice.
			$newText = preg_replace_callback(
				"~(<{$tag}\b[^>]*\bhash=\")([0-9a-f]+)(\"[^>]*>)(.*?)(</{$tag}\s*>)~su",
				static function ( $match ) use ( $secret ) {
					$localHash = hash_hmac( 'sha256', $match[4], $secret );
					return $match[1] . $localHash . $match[3] . $match[4] . $match[5];
				},
				$wikitext
			);

			$title = $wikiPage->getTitle()->getPrefixedText();
			if ( $newText === $wikitext ) {
				$unchanged++;
				continue;
			}
			$wikiPage->doUserEditContent(
				ContentHandler::makeContent( $newText, $wikiPage->getTitle() ),
				$user,
				'dev: re-sign shtml blocks with the local SecureHTML key',
				EDIT_UPDATE | EDIT_FORCE_BOT
			);
			$this->output( "    re-signed: $title\n" );
			$resigned++;
		}
		$this->output( "done — $resigned page(s) re-signed, $unchanged already current.\n" );
	}

}

require_once RUN_MAINTENANCE_IF_MAIN;
