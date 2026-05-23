<?php
# Site-wide MediaWiki config for MaccabiPedia. Loaded by LocalSettings.php
# AFTER LocalSettings.env.*.php so env-specific values (DB, URL, secrets,
# cache, logs, debug verbosity) are already set. Do NOT put env-specific
# lines here — see LocalSettings.env.local.php / LocalSettings.env.prod.php.
#
# See includes/DefaultSettings.php for all configurable settings
# and their default values, but don't forget to make changes in _this_
# file, not there.
#
# Further documentation for configuration settings may be found at:
# https://www.mediawiki.org/wiki/Manual:Configuration_settings

# Protect against web entry
if (!defined('MEDIAWIKI')) {
	exit;
}

## Uncomment this to disable output compression
# $wgDisableOutputCompression = true;

$wgSitename = "מכביפדיה";

$wgLocaltimezone = "Asia/Jerusalem";


## The URL base path to the directory containing the wiki;
# $wgScriptPath — set in LocalSettings.env.*.php
# $wgArticlePath — set in LocalSettings.env.*.php

## The protocol and server name to use in fully-qualified URLs
# $wgServer — set in LocalSettings.env.*.php

## The URL path to static resources (images, scripts, etc.)
$wgResourceBasePath = $wgScriptPath;


## UPO means: this is also a user preference option

# $wgEnableEmail — set in LocalSettings.env.*.php
$wgEnableUserEmail = true; # UPO

# $wgEmergencyContact — set in LocalSettings.env.*.php
# $wgPasswordSender — set in LocalSettings.env.*.php

$wgEnotifUserTalk = false; # UPO
$wgEnotifWatchlist = false; # UPO
# $wgEmailAuthentication — set in LocalSettings.env.*.php

## Allow use <img> tag
$wgAllowExternalImages = true; # -- due to upgrade

## Database settings
# $wgDBtype — set in LocalSettings.env.*.php
# $wgDBserver — set in LocalSettings.env.*.php
# $wgDBname — set in LocalSettings.env.*.php
# $wgDBuser — set in LocalSettings.env.*.php
# $wgDBpassword — set in LocalSettings.env.*.php


# MySQL specific settings
# $wgDBprefix — set in LocalSettings.env.*.php

# MySQL table options to use during installation or update
$wgDBTableOptions = "ENGINE=InnoDB, DEFAULT CHARSET=binary";

## Shared memory settings
# $wgMainCacheType — set in LocalSettings.env.*.php
# $wgMemCachedServers — set in LocalSettings.env.*.php

## Use file-system file caching (https://www.mediawiki.org/wiki/Manual:File_cache)
## This seems to be not working well always, because the cache files name based on the page names (which contains hebrew) - they will be encoded and having too long path
## $wgUseFileCache = true;

## To enable image uploads, make sure the 'images' directory
## is writable, then set this to true:
$wgEnableUploads = true;
// Add several file types to the default array
$wgFileExtensions = array_merge($wgFileExtensions, ['pdf']);

#$wgUseImageMagick = true;
#$wgImageMagickConvertCommand = "/usr/bin/convert";

# InstantCommons allows wiki to use images from https://commons.wikimedia.org
$wgUseInstantCommons = false;

# Periodically send a pingback to https://www.mediawiki.org/ with basic data
# about this MediaWiki instance. The Wikimedia Foundation shares this data
# with MediaWiki developers to help guide future development efforts.
$wgPingback = true;

## If you use ImageMagick (or any other shell command) on a
## Linux server, this will need to be set to the name of an
## available UTF-8 locale
$wgShellLocale = "en_US.utf8";

## Set $wgCacheDirectory to a writable directory on the web server
## to make your wiki go slightly faster. The directory should not
## be publically accessible from the web.
#$wgCacheDirectory = "$IP/cache";

# Site language code, should be one of the list in ./languages/data/Names.php
$wgLanguageCode = "he";

# $wgSecretKey — set in LocalSettings.env.*.php

# Changing this will log out all existing sessions.
$wgAuthenticationTokenVersion = "1";

# Site upgrade key. Must be set to a string (default provided) to turn on the
# web installer while LocalSettings.php is in place
# $wgUpgradeKey — set in LocalSettings.env.*.php

## For attaching licensing metadata to pages, and displaying an
## appropriate copyright notice / icon. GNU Free Documentation
## License and Creative Commons licenses are supported so far.
$wgRightsPage = ""; # Set to the title of a wiki page that describes your license/copyright
$wgRightsUrl = "";
$wgRightsText = "";
$wgRightsIcon = "";

# Path to the GNU diff3 utility. Used for conflict resolution.
$wgDiff3 = "";

# The following permissions were set based on your choice in the installer
$wgGroupPermissions['*']['edit'] = false;
$wgGroupPermissions['user']['edit'] = true;
$wgGroupPermissions['sysop']['edit'] = true;

# The default 'move' permission is set to True for every registered authenticated user, we want only sysops to allow move files and pages
$wgGroupPermissions['user']['move'] = true;
$wgGroupPermissions['sysop']['move'] = true;


# Allow bots to delete pages
$wgGroupPermissions['bot']['delete'] = true;
$wgGroupPermissions['bot']['deletedhistory'] = true; // optional

# In order to be at the 'autocomfirmed' group 'משתמשים ותיקים', we want any user to be registered for 2 weeks and have at least 3 edits
$wgAutoConfirmAge = 86400 * 14;   // 14 days
$wgAutoConfirmCount = 3;

# $wgEmailConfirmToEdit — set in LocalSettings.env.*.php (true on prod, false
# locally where email is disabled and no address can be confirmed).

# Enable images lazy loading
$wgNativeImageLazyLoading = true;

## Default skin: you can change the default skin. Use the internal symbolic
## names, ie 'vector', 'monobook':
$wgDefaultSkin = "Metrolook";

# Enabled skins. Maccabipedia is loaded as an opt-in option (selectable
# via ?useskin=maccabipedia or via Special:Preferences); default stays
# Metrolook until the new skin is verified.
wfLoadSkin('Metrolook');
wfLoadSkin('Maccabipedia');


// For debugging, dont remove this! just comment out.
// $wgDebugLogFile = "$IP/MyLogs/debug-{$wgDBname}.log";
# $wgDBerrorLog — set in LocalSettings.env.*.php
# $wgResourceLoaderDebug — set in LocalSettings.env.*.php


# OutputPageBeforeHTML Hook to add tags on head
$wgHooks['BeforePageDisplay'][] = function ($out, &$text) {
	$out->addHeadItem('Assistant-font', '<link rel="preconnect" href="https://fonts.googleapis.com">');
	$out->addHeadItem('Assistant-font', '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>');
	$out->addHeadItem('Assistant-font', '<link href="https://fonts.googleapis.com/css2?family=Assistant:wght@200..800&display=swap" rel="stylesheet">');
	$out->addHeadItem('font-awsome', '<link rel="stylesheet" href="https://use.fontawesome.com/releases/v6.5.2/css/all.css" crossorigin="anonymous">');
	return true;
};

# Php debugging:
// error_reporting( -1 );
// ini_set( 'display_errors', 1 );

# $wgDebugLogGroups — set in LocalSettings.env.*.php


# $wgShowDBErrorBacktrace — set in LocalSettings.env.*.php

# MaccabiPedia special configurations:
# $wgHiddenPrefs = array(0 => 'language', 1 => 'skin'); 		# Hide Languages and Skins from user's selection
# $wgJobRunRate — set in LocalSettings.env.*.php  # https://www.mediawiki.org/wiki/Manual:$wgJobRunRate
$wgCountCategorizedImagesAsUsed = true;				 		# Considers categorized images as used (מיוחד:קבצים_שאינם_בשימוש)
$wgExternalLinkTarget = '_blank'; 							# Opens External links in new tab
$wgFavicon = "/favicon.ico"; 								# Enable Favicon
$wgAppleTouchIcon = "/favicon.ico"; 						# Enable Favicon for Apple Devices
$wgAllowSiteCSSOnRestrictedPages = 1; 						# Enable CSS on Login Page
$wgExpensiveParserFunctionLimit = 10000; 						# Enable 10000 Expensive Parser Function Limit


$wgMaxArticleSize = 8192;  // This is to avoid the "<!-- WARNING: template omitted, post-expand include size too large -->" msg (caused atleast in שרן ייני page).

$wgMaxImageArea = 2.5e7;  # Allow to show preview of image up to 36 million pixels or 6000×6000, https://www.mediawiki.org/wiki/Manual:$wgMaxImageArea
$wgMaxShellMemory = 512000;  # Use up to 512MIB of virtual memory, https://www.mediawiki.org/wiki/Manual:$wgMaxShellMemory
$wgMemoryLimit = 268435456; # https://www.mediawiki.org/wiki/Manual:$wgMemoryLimit


define("NS_שיר", 3000); // This MUST be even.
define("NS_שיחת_שיר", 3001);
define("NS_כדורעף", 3001);
define("NS_שיחת_כדורעף", 3002);
define("NS_כדורסל", 3003);
define("NS_שיחת_כדורסל", 3004);
define("NS_כדורגל", 3010);
define("NS_שיחת_כדורגל", 3011);
define("NS_כדוריד", 3020);
define("NS_שיחת_כדוריד", 3021);

$wgExtraNamespaces[NS_שיר] = "שיר";
$wgExtraNamespaces[NS_שיחת_שיר] = "שיחת_שיר";
$wgExtraNamespaces[NS_כדורעף] = "כדורעף";
$wgExtraNamespaces[NS_שיחת_כדורעף] = "שיחת_כדורעף";
$wgExtraNamespaces[NS_כדורסל] = "כדורסל";
$wgExtraNamespaces[NS_שיחת_כדורסל] = "שיחת_כדורסל";
$wgExtraNamespaces[NS_כדורגל] = "כדורגל";
$wgExtraNamespaces[NS_שיחת_כדורגל] = "שיחת_כדורגל";
$wgExtraNamespaces[NS_כדוריד] = "כדוריד";
$wgExtraNamespaces[NS_שיחת_כדוריד] = "שיחת_כדוריד";

// Add these namespaces to be shown as default when searching on maccabipedia - without choosing "all" section in the search results)
$wgNamespacesToBeSearchedDefault[NS_שיר] = true;
$wgNamespacesToBeSearchedDefault[NS_שיחת_שיר] = true;
$wgNamespacesToBeSearchedDefault[NS_כדורעף] = true;
$wgNamespacesToBeSearchedDefault[NS_שיחת_כדורעף] = true;
$wgNamespacesToBeSearchedDefault[NS_כדורסל] = true;
$wgNamespacesToBeSearchedDefault[NS_שיחת_כדורסל] = true;
$wgNamespacesToBeSearchedDefault[NS_כדורגל] = true;
$wgNamespacesToBeSearchedDefault[NS_שיחת_כדורגל] = true;
$wgNamespacesToBeSearchedDefault[NS_כדוריד] = true;
$wgNamespacesToBeSearchedDefault[NS_שיחת_כדוריד] = true;



require_once "$IP/extensions/NumberFormat/NumberFormat.php"; 		# Number Format ( {{#number_format:}} ) [ https://www.mediawiki.org/wiki/Extension:NumberFormat ]

// wfLoadExtension( 'HidePrefix' ); # Hide Prefix {Namespaces) from links https://www.mediawiki.org/wiki/Extension:HidePrefix
wfLoadExtension('Loops'); # Loops ( {{#loop:}} ) https://www.mediawiki.org/wiki/Extension:Loops
$egLoopsCountLimit = -1;

wfLoadExtension('Arrays');                    # Arrays https://www.mediawiki.org/wiki/Extension:Arrays
wfLoadExtension('AdminLinks');				# Admin Links (מיוחד: קישורי מפעיל) [ https://www.mediawiki.org/wiki/Extension:Admin_Link
wfLoadExtension('AutoCreateCategoryPages'); 	# Auto Create Category Pages https://www.mediawiki.org/wiki/Extension:Auto_Create_Category_Pages
wfLoadExtension('MixedNamespaceSearchSuggestions'); # https://www.mediawiki.org/wiki/Extension:MixedNamespaceSearchSuggestions
wfLoadExtension('DynamicPageList3');			# https://www.mediawiki.org/wiki/Extension:DynamicPageList3

wfLoadExtension('EmbedVideo'); 				# Embed Video ( {{#ev:}} ) https://www.mediawiki.org/wiki/Extension:EmbedVideo
// Remove the need to approve before each video is being rendered (there's a play button anyway)
$wgEmbedVideoRequireConsent = false;

wfLoadExtension('LinkSuggest'); 				# Link Suggests for editors https://www.mediawiki.org/wiki/Extension:LinkSuggest 
wfLoadExtension('SimpleBatchUpload'); 		# Upload Batch of files (מיוחד:BatchUpload) https://www.mediawiki.org/wiki/Extension:SimpleBatchUpload
wfLoadExtension('Variables'); 				# https://www.mediawiki.org/wiki/Extension:Variables
wfLoadExtension('TemplateSandbox'); // https://www.mediawiki.org/wiki/Extension:TemplateSandbox
wfLoadExtension('DebugTemplates'); // https://www.mediawiki.org/wiki/Extension:DebugTemplates
wfLoadExtension('LastUserLogin'); //https://www.mediawiki.org/wiki/Extension:LastUserLogin
wfLoadExtension('JSBreadCrumbs');  // https://www.mediawiki.org/wiki/Extension:JSBreadCrumbs

wfLoadExtension('WikiSEO'); // https://www.mediawiki.org/wiki/Extension:WikiSEO, need to transform our data from 1.x.x to 2.x.x (check the extension link)
$wgWikiSeoDefaultImage = 'File:Maccabipedia logo.png';
$wgTwitterSiteHandle = '@maccabipedia';

# Core logo. No skin actually uses it (Metrolook + Maccabipedia each render
# their own app-header logo), but WikiSEO reads it for the schema.org
# publisher logo in its JSON-LD — left unset it falls back to MediaWiki's
# change-your-logo.svg placeholder. Point it at the same image as
# $wgWikiSeoDefaultImage above: the uploaded File "Maccabipedia logo.png"
# (e/e6 = MD5 of that filename; stable unless the File is renamed). We build
# from $wgScriptPath, not $wgUploadPath — the latter is still false at
# LocalSettings time (core resolves it later in Setup.php). NOTE: this image
# lives on prod's wiki, so the URL 404s on the local replica; that's
# harmless — it only affects SEO metadata, which dev never renders.
$wgLogos = [ '1x' => "$wgScriptPath/images/e/e6/Maccabipedia_logo.png" ];

// Welcome any new user with our default msg
wfLoadExtension('NewUserMessage');  //https://www.mediawiki.org/wiki/Extension:NewUserMessage

wfLoadExtension('ReplaceSet'); 				# https://www.mediawiki.org/wiki/Extension:ReplaceSet, a bit old - worth to replace, {{#replaceset:}}
$egReplaceSetCallLimit = 5000;  # Change the maximum ReplaceSet usage in one page (https://www.mediawiki.org/wiki/Extension:ReplaceSet)
$egReplaceSetPregLimit = 5000;  # Change the maximum ReplaceSet usage in one page (https://www.mediawiki.org/wiki/Extension:ReplaceSet)

wfLoadExtension('PageForms'); // https://www.mediawiki.org/wiki/Extension:Page_Forms
$wgPageFormsSimpleUpload = true;

// Built in:
wfLoadExtension('VisualEditor'); // https://www.mediawiki.org/wiki/Extension:VisualEditor
wfLoadExtension('Nuke'); // https://www.mediawiki.org/wiki/Extension:Nuke
wfLoadExtension('ReplaceText');
wfLoadExtension('Renameuser');
wfLoadExtension('Poem');
wfLoadExtension('MultimediaViewer');
wfLoadExtension('PdfHandler');
wfLoadExtension('CodeEditor');
wfLoadExtension('ConfirmEdit');
wfLoadExtension('CategoryTree');
wfLoadExtension('Cite');
wfLoadExtension('CiteThisPage');
//wfLoadExtension( 'DeleteBatch' );


wfLoadExtension('WikiEditor'); # Enable WikiEditor  (גרסא ישנה של העורך, היות שבגרסאות החדשות הוסר טאב "שינויים אחרונים")
$wgDefaultUserOptions['usebetatoolbar'] = 1; # Enables use of WikiEditor by default but still allows users to disable it in preferences
$wgDefaultUserOptions['usebetatoolbar-cgd'] = 1; # Enables link and table wizards by default but still allows users to disable them in preferences
$wgDefaultUserOptions['wikieditor-preview'] = 1; # Enables the Preview and Changes tabs
$wgDefaultUserOptions['wikieditor-publish'] = 0; # Displays the Publish and Cancel buttons on the top right side

wfLoadExtension('ParserFunctions'); # Enable Parser Functions [ https://www.mediawiki.org/wiki/Extension:ParserFunctions ]
$wgPFEnableStringFunctions = true; # Allows to activate the integrated string function functionality
$wgPFStringLengthLimit = 10000; # Set max StringFunctions limit to be 10k
$wgStringFunctionsLimitReplace = 10000;
$wgStringFunctionsLimitSearch = 10000;

// wfLoadExtension('WhosOnline');  //https://www.mediawiki.org/wiki/Extension:WhosOnline due to upgrade
$wgWhosOnlineShowAnons = false;

wfLoadExtension('Maintenance'); // https://www.mediawiki.org/wiki/Extension:Maintenance
$wgGroupPermissions['sysop']['maintenance'] = true;

wfLoadExtension('SecureHTML');				#SecureHTML [https://www.mediawiki.org/wiki/Extension:Secure_HTML]
# $wgSecureHTMLSecrets — set in LocalSettings.env.*.php

wfLoadExtension('Scribunto');
$wgScribuntoDefaultEngine = 'luastandalone';

require_once "$IP/extensions/UserFunctions/UserFunctions.php"; # User Functions ( {{#ifsysop:}} ) [ https://www.mediawiki.org/wiki/Extension:UserFunctions ]
$wgUFAllowedNamespaces = array_fill(0, 200, true);


# $wgShowSQLErrors — set in LocalSettings.env.*.php
# $wgShowExceptionDetails — set in LocalSettings.env.*.php
$wgCargoMaxQueryLimit = 50000;
$wgCargoAllowedSQLFunctions[] = array('REPLACE', 'COALESCE', 'IF', 'DATE_FORMAT', 'TRIM', 'DISTINCT', 'DAYOFWEEK', 'IFNULL');  # Needed for the Tifo template
wfLoadExtension('Cargo');						# Cargo https://www.mediawiki.org/wiki/Extension:Cargo

// Not sure if works:
// wfLoadExtension( 'MagicNoCache' ); // https://www.mediawiki.org/wiki/Extension:MagicNoCache

// Does not work with the auto-completion of the categories
wfLoadExtension('CodeMirror');  // https://www.mediawiki.org/wiki/Extension:CodeMirror
$wgDefaultUserOptions['usecodemirror'] = 1;

// https://www.mediawiki.org/wiki/Extension:ContactPage
wfLoadExtension('ContactPage');
$wgContactConfig['default'] = [
	'RecipientUser' => 'Kosh', // Must be the name of a valid account which also has a verified e-mail-address added to it.
	'SenderName' => 'Contact Form on ' . $wgSitename, // "Contact Form on" needs to be translated
	'SenderEmail' => null, // Defaults to $wgPasswordSender, may be changed as required
	'RequireDetails' => true, // Either "true" or "false" as required
	'IncludeIP' => true, // Either "true" or "false" as required
	'MustBeLoggedIn' => false, // Check if the user is logged in before rendering the form. Either "true" or "false" as required
	'AdditionalFields' => [
		'Text' => [
			'label-message' => 'emailmessage',
			'type' => 'textarea',
			'rows' => 20,
			'required' => true,  // Either "true" or "false" as required
		],
	],
	// Added in MW 1.26
	'DisplayFormat' => 'table',  // See HTMLForm documentation for available values.
	'RLModules' => [],  // Resource loader modules to add to the form display page.
	'RLStyleModules' => []  // Resource loader CSS modules to add to the form display page.
];



$wgDplSettings['maxResultCount'] = 15000;  # Allow unlimited results on dpl, We might have some old queries that we dont limit the count for them, so we have to write here a number that will be bigger than any category we have (which is probably "Category:Games")
# Dont use allowUnlimitedResults, this will prevent us from using "count" parametre in the queries

$wgReplaceTextResultsLimit = 1000;  # Change the default max pages of replace text (250) to something we can work with (replace in all games pages)


wfLoadExtension('TabberNeue'); // https://www.mediawiki.org/wiki/Extension:TabberNeue
$wgTabberNeueUpdateLocationOnTabChange = true;
$wgTabberNeueEnableAnimation = false;
$wgTabberNeueParseTabName = true;

#wfLoadExtension('GoogleRichCards'); //https://www.mediawiki.org/wiki/Extension:GoogleRichCards
// Enable annotations for articles
#$wgGoogleRichCardsAnnotateArticles = true;
// Enable annotations for events
#$wgGoogleRichCardsAnnotateEvents = true;
// Enable WebSite annotations
#$wgGoogleRichCardsAnnotateWebSite = true;


wfLoadExtension('GTag');
# $wgGTagAnalyticsId — set in LocalSettings.env.*.php
// require_once "$IP/extensions/googleAnalytics/googleAnalytics.php"; # https://www.mediawiki.org/wiki/Extension:Google_Analytics_Integration
// $wgGoogleAnalyticsAccount = 'UA-123078340-2';  # MaccabiPedi


$wgResourceModules['maccabipedia.customizations'] = array(
	'styles' => ["slick/slick.less", "slick/slick-theme.less"],
	'scripts' => ["slick/slick.min.js", "canvasjs/jquery.canvasjs.min.js"],
	'dependencies' => ['jquery'],
	'localBasePath' => "$IP/customizations/",
	'remoteBasePath' => "$wgScriptPath/customizations/",
	'position' => 'top'
);

$wgResourceLoaderMaxage = ['versioned' => 31536000, 'unversioned' => 86400];

$wgHooks['BeforePageDisplay'][] = function (&$out) {
	$out->addModules('ext.customScripts');
};

wfLoadExtension('RegexFunctions');

function efCustomBeforePageDisplay(&$out, &$skin)
{
	$out->addModules(array('maccabipedia.customizations'));
}

$wgHooks['BeforePageDisplay'][] = 'efCustomBeforePageDisplay';
