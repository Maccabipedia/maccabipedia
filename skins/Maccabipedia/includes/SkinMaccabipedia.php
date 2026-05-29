<?php
/**
 * Maccabipedia skin — successor to Metrolook.
 *
 * SkinMustache-based skin built around declarative data builders + mustache
 * iteration. The skin's responsibilities, roughly: build menu data arrays
 * (`getTemplateData()` and helpers), set the body class + viewport, and
 * delegate everything else to MW core.
 *
 * This is the default skin. Its LESS/JS source lives under
 * `skins/Maccabipedia/` (own `skins.maccabipedia.*` ResourceLoader modules,
 * no runtime dependency on Metrolook). The legacy Metrolook skin stays
 * vendored at `skins/Metrolook/` as an opt-in fallback and is no longer
 * maintained.
 *
 * @file
 * @ingroup Skins
 * @license GPL-2.0-or-later
 */

namespace MediaWiki\Skin\Maccabipedia;

use Html;
use OutputPage;
use SkinMustache;
use SpecialPage;
use Title;

class SkinMaccabipedia extends SkinMustache {

	public function initPage( OutputPage $out ) {
		parent::initPage( $out );
		// Mobile viewport — without it, iPhones render at 1000px desktop width.
		$out->addMeta( 'viewport', 'width=device-width, initial-scale=1' );
		$out->addModuleStyles( [
			'skins.maccabipedia.styles',
			'skins.maccabipedia.interface',
		] );
		$out->addModules( [ 'skins.maccabipedia.js' ] );
	}

	public function getTemplateData() {
		$data = parent::getTemplateData();
		// SkinMustache's default `html-title-heading` wraps the title in
		// <h1 class="firstHeading">; our `.firstHeading` rule has font-size:140%
		// which would scale the .mw-page-title-main span inside the yellow
		// .maccabipedia-page-title bar from 1.1rem to ~25px. Match Metrolook's
		// $this->html('title') emission — bare <span class="mw-page-title-main">
		// via OutputPage::getPageTitle().
		$data['html-title-heading'] = $this->getOutput()->getPageTitle();
		$data['data-app-header'] = $this->buildAppHeaderData();
		$data['data-app-footer'] = $this->buildAppFooterData();
		$data['html-search-input'] = $this->buildSearchInputHtml();
		$data['html-footer-info-items'] = $this->buildFooterInfoHtml( $data );
		return $data;
	}

	private function buildAppHeaderData(): array {
		$skinAssetsBase = $this->getConfig()->get( 'Server' )
			. $this->getConfig()->get( 'ScriptPath' )
			. '/skins/Maccabipedia/assets/';
		return [
			'logo-url'         => Title::newMainPage()->getLocalURL(),
			// The skin renders its own logo here, not core's mw-logo element, so
			// the SkinModule `logo` feature stays OFF in skin.json — enabling it
			// preloads an unused logo (the change-your-logo.svg placeholder absent
			// $wgLogos) and the browser warns "preloaded but not used".
			'logo-image-src'   => $skinAssetsBase . 'images/logo.png',
			'primary-dropdowns' => $this->buildPrimaryDropdowns(),
			'standalone-link'  => [
				'url'   => $this->pageUrl( 'מכבימדיה' ),
				'label' => 'מכבימדיה',
			],
			'options-panel'    => $this->buildOptionsPanel(),
		];
	}

	private function buildPrimaryDropdowns(): array {
		$dropdowns = [
			[ 'heading' => 'מכבי תל אביב', 'items' => [
				[ 'label' => 'ההיסטוריה', 'title' => 'קטגוריה: היסטוריה' ],
				[ 'label' => 'עונות',     'title' => 'עונות' ],
				[ 'label' => 'מתקנים',    'title' => 'פורטל מתקנים' ],
				[ 'label' => 'מפעלים',    'title' => 'פורטל מפעלים' ],
				[ 'label' => 'מדים',      'title' => 'פורטל מדים' ],
				[ 'label' => 'תארים',     'title' => 'תארים' ],
			] ],
			[ 'heading' => 'שחקנים וצוות', 'items' => [
				[ 'label' => 'שחקנים',    'title' => 'פורטל שחקנים' ],
				[ 'label' => 'אנשי צוות', 'title' => 'פורטל אנשי צוות' ],
			] ],
			[ 'heading' => 'אוהדים ותרבות', 'items' => [
				[ 'label' => 'שירים',           'title' => 'שירי קהל' ],
				[ 'label' => 'כרטיסים ומנויים', 'title' => 'כרטיסים ומנויים' ],
				[ 'label' => 'כרזות',           'title' => 'כרזות משחק' ],
				[ 'label' => 'קלפים ומדבקות',  'title' => 'קלפים ומדבקות' ],
				[ 'label' => 'תפאורות',         'title' => 'קטגוריה: תפאורות' ],
				[ 'label' => 'ארגונים',         'title' => 'ארגוני אוהדים' ],
				[ 'label' => 'ספרים',           'title' => 'ספריה צהובה' ],
				[ 'label' => 'פנזינים',         'title' => 'קטגוריה: פנזינים' ],
			] ],
			[ 'heading' => 'משחקים', 'items' => [
				[ 'label' => 'חיפוש משחק',   'title' => 'חיפוש משחק' ],
				[ 'label' => 'סטטיסטיקות',   'title' => 'סטטיסטיקות' ],
			] ],
		];
		// Resolve URLs once (mustache iterates structurally).
		foreach ( $dropdowns as &$group ) {
			foreach ( $group['items'] as &$item ) {
				$item['url'] = $this->pageUrl( $item['title'] );
			}
		}
		return $dropdowns;
	}

	private function buildOptionsPanel(): array {
		$title = $this->getTitle();
		$relevantTitle = $this->getRelevantTitle();
		$user = $this->getUser();
		$request = $this->getRequest();
		$currentAction = $request->getRawVal( 'action' );
		$currentOldid = $request->getInt( 'oldid', 0 );
		$isViewingEditForm = $currentAction === 'edit';
		$pageNamespace = $title->getNamespace();

		// Only the edit dropdown is hidden on Special: / Media: namespaces —
		// those pages have no editable wikitext / talk page / history. The
		// user dropdown and the global options dropdown still render so a
		// reader on Special:Recentchanges can still log in / open settings.
		$showEditDropdown = !in_array( $pageNamespace, [ NS_SPECIAL, NS_MEDIA ], true );

		$actionURL = static function ( string $action, array $extra = [] )
				use ( $relevantTitle, $currentOldid ): string {
			$params = [ 'action' => $action ] + $extra;
			if ( $currentOldid > 0 ) {
				$params['oldid'] = $currentOldid;
			}
			return $relevantTitle->getLocalURL( $params );
		};

		[ 'talk' => $talkURL, 'subject' => $subjectURL ] = $this->getTalkSubjectPair( $title );

		$editIconURL = $isViewingEditForm
			? $relevantTitle->getLocalURL()
			: $actionURL( 'edit' );

		return [
			'edit' => $showEditDropdown ? [
				'icon-url'           => $editIconURL,
				'is-editing'         => $isViewingEditForm,
				'can-edit'           => $user->isAllowed( 'edit' ),
				'edit-action-url'    => $actionURL( 'edit' ),
				'view-url'           => $relevantTitle->getLocalURL(),
				'talk-page-url'      => $talkURL,
				'subject-page-url'   => $subjectURL,
				'show-subject-back'  => $subjectURL !== null && $currentAction === null,
				'history-url'        => $actionURL( 'history' ),
				'purge-url'          => $actionURL( 'purge', [ 'forcerecursivelinkupdate' => 1 ] ),
				'is-admin'           => $user->isAllowed( 'protect' ),
				'delete-url'         => $actionURL( 'delete' ),
				'move-url'           => SpecialPage::getTitleFor( 'Movepage', $relevantTitle->getPrefixedText() )->getLocalURL(),
				'protect-url'        => $actionURL( 'protect' ),
			] : false,
			'user' => $this->buildUserPanel( $user ),
			'options' => [
				[ 'url' => SpecialPage::getTitleFor( 'Recentchanges' )->getLocalURL(), 'label' => 'שינויים אחרונים' ],
				[ 'url' => SpecialPage::getTitleFor( 'Upload' )->getLocalURL(),        'label' => 'העלאת קובץ' ],
				[ 'url' => SpecialPage::getTitleFor( 'Whatlinkshere', $relevantTitle->getPrefixedText() )->getLocalURL(), 'label' => 'דפים מקושרים' ],
				[ 'url' => $this->pageUrl( 'מיוחד:קישורי מפעיל' ),                     'label' => 'קישורי מפעיל' ],
			],
		];
	}

	/**
	 * Custom Hebrew namespaces in `LocalSettings.shared.php` use non-standard
	 * IDs that break MediaWiki's even=subject / odd=talk pairing convention,
	 * so we pair them explicitly here. Each constant is `defined()`-guarded
	 * so a missing namespace constant in a stripped-down environment doesn't
	 * fatal the wiki — the corresponding talk-link silently skips instead.
	 *
	 * @return array{talk: ?string, subject: ?string}
	 */
	private function getTalkSubjectPair( Title $title ): array {
		$customPairs = [
			'NS_שיר'    => 'NS_שיחת_שיר',
			'NS_כדורעף' => 'NS_שיחת_כדורעף',
			'NS_כדורסל' => 'NS_שיחת_כדורסל',
			'NS_כדורגל' => 'NS_שיחת_כדורגל',
			'NS_כדוריד' => 'NS_שיחת_כדוריד',
		];
		$subjectToTalk = [];
		foreach ( $customPairs as $subjectName => $talkName ) {
			if ( defined( $subjectName ) && defined( $talkName ) ) {
				$subjectToTalk[ constant( $subjectName ) ] = constant( $talkName );
			}
		}
		foreach ( [ NS_MAIN, NS_USER, NS_PROJECT, NS_FILE, NS_MEDIAWIKI, NS_TEMPLATE, NS_HELP, NS_CATEGORY ] as $ns ) {
			$subjectToTalk[ $ns ] = $ns + 1;
		}
		$talkToSubject = array_flip( $subjectToTalk );

		$pageNs = $title->getNamespace();
		$talkURL = null;
		$subjectURL = null;
		if ( isset( $subjectToTalk[ $pageNs ] ) ) {
			$talkURL = Title::makeTitle( $subjectToTalk[ $pageNs ], $title->getText() )->getLocalURL();
		} elseif ( isset( $talkToSubject[ $pageNs ] ) ) {
			$subjectURL = Title::makeTitle( $talkToSubject[ $pageNs ], $title->getText() )->getLocalURL();
		}
		return [ 'talk' => $talkURL, 'subject' => $subjectURL ];
	}

	private function buildUserPanel( $user ): array {
		if ( $user->isRegistered() ) {
			$userName = $user->getName();
			return [
				'is-registered'     => true,
				'name'              => $userName,
				'profile-url'       => $this->pageUrl( 'משתמש:' . $userName ),
				'talk-url'          => $this->pageUrl( 'שיחת משתמש:' . $userName ),
				'preferences-url'   => SpecialPage::getTitleFor( 'Preferences' )->getLocalURL(),
				'contributions-url' => SpecialPage::getTitleFor( 'Contributions', $userName )->getLocalURL(),
				'logout-url'        => SpecialPage::getTitleFor( 'Userlogout' )->getLocalURL(),
			];
		}
		return [
			'is-registered'      => false,
			'name'               => 'משתמש',
			'login-url'          => SpecialPage::getTitleFor( 'Userlogin' )->getLocalURL(),
			'create-account-url' => SpecialPage::getTitleFor( 'CreateAccount' )->getLocalURL(),
			'talk-url'           => $this->pageUrl( 'מיוחד:השיחה שלי' ),
		];
	}

	private function buildAppFooterData(): array {
		$mwResourceURL = $this->getConfig()->get( 'Server' )
			. $this->getConfig()->get( 'ScriptPath' )
			. '/resources/assets/';
		return [
			'about-links' => [
				[ 'url' => $this->pageUrl( 'מכביפדיה: תרומות' ),  'label' => 'תרומות' ],
				[ 'url' => $this->pageUrl( 'מכביפדיה: צור קשר' ), 'label' => 'יצירת קשר' ],
			],
			// TODO: replace bit.ly URL shorteners with canonical URLs (creates
			// operational risk: account churn, ad-blocker breakage, no record
			// of resolution targets).
			'social-links' => [
				[ 'icon' => 'fa-facebook-f', 'url' => 'https://bit.ly/visit_mp_fb' ],
				[ 'icon' => 'fa-x-twitter',  'url' => 'https://bit.ly/visit_mp_x' ],
				[ 'icon' => 'fa-instagram',  'url' => 'https://bit.ly/visit_mp_i' ],
				[ 'icon' => 'fa-youtube',    'url' => 'https://bit.ly/visit_mp_y' ],
			],
			'powered-by-mw-image-url' => $mwResourceURL . 'poweredby_mediawiki_88x31.png',
		];
	}

	/**
	 * Search input — Metrolook used $this->makeSearchInput(['class' => 'text-field']).
	 * SkinMustache's data-search-box.html-input has no class hook, so we build
	 * the input ourselves to keep the .text-field CSS rules in app-header.less
	 * applying.
	 */
	private function buildSearchInputHtml(): string {
		return Html::input( 'search', '', 'search', [
			'id'          => 'searchInput',
			'class'       => 'text-field',
			'placeholder' => $this->msg( 'search' )->text(),
			'autocomplete' => 'off',
		] );
	}

	/**
	 * Pluck the `info` section's html-items out of SkinMustache's
	 * `data-footer.array-items` for rendering inside the credits row.
	 * Returns the section's pre-rendered <ul> as-is — mustache renders it
	 * via {{{html-footer-info-items}}}.
	 */
	private function buildFooterInfoHtml( array $data ): string {
		foreach ( $data['data-footer']['array-items'] ?? [] as $section ) {
			if ( ( $section['name'] ?? '' ) === 'info' ) {
				return $section['html-items'] ?? '';
			}
		}
		return '';
	}

	private function pageUrl( string $titleText ): string {
		$title = Title::newFromText( $titleText );
		return $title ? $title->getLocalURL() : '#';
	}
}
