<?php
# Env-specific config for the local docker wiki.
# Loaded by LocalSettings.php BEFORE LocalSettings.shared.php, so shared
# code can reference vars set here ($wgScriptPath, $wgDBname, etc).
#
# Prod gets its own sibling (LocalSettings.env.prod.php, never committed
# here) with the matching set of assignments. Keep the *set of variables*
# in lock-step with that file — add a var here only after the prod
# counterpart has a value for it.

if (!defined('MEDIAWIKI')) {
	exit;
}

## URL — pretty-URL article path, mirrors prod. The .htaccess at the
## docroot (mounted via docker-compose from config/htaccess) routes
## "/foo" → "index.php?title=foo" via mod_rewrite; AllowOverride is
## enabled in config/apache-allow-override.conf.
$wgServer = getenv('MW_SITE_SERVER') ?: 'http://localhost:8080';
$wgScriptPath = '';
$wgArticlePath = '/$1';

## Email — disabled locally, no SMTP reachable.
$wgEnableEmail = false;
$wgEmailAuthentication = false;
## No email system locally, so no address can be confirmed — don't gate editing
## on it. Prod's LocalSettings.env.prod.php must set this TRUE to keep the gate.
$wgEmailConfirmToEdit = false;
$wgEmergencyContact = 'dev@localhost';
$wgPasswordSender = 'dev@localhost';

## Database — values come from docker-compose environment.
$wgDBtype = 'mysql';
$wgDBserver = getenv('MW_DB_HOST') ?: 'mariadb';
$wgDBname = getenv('MW_DB_NAME') ?: 'maccabipedia';
$wgDBuser = getenv('MW_DB_USER') ?: 'mw';
$wgDBpassword = getenv('MW_DB_PASSWORD') ?: 'devpass';
$wgDBprefix = getenv('MW_DB_PREFIX') ?: 'MPMW_';

## Cache — disabled so edits and template changes show immediately.
$wgMainCacheType = CACHE_NONE;
$wgMemCachedServers = [];

## Secrets — placeholders only. Prod's env file carries the real values.
$wgSecretKey = 'dev-secret-not-a-real-key-local-only';
$wgUpgradeKey = 'dev-upgrade-key-local-only';

## Logging — no files written (no /MyLogs dir in the container). Errors
## surface on Apache's stderr, which docker compose captures. Route PHP
## notices/warnings to the log (visible via `docker compose logs mediawiki`),
## NOT the response body: a notice emitted while LocalSettings loads (e.g. an
## extension's deprecated-entry-point wfWarn) would otherwise print before
## headers are sent and break every page with "headers already sent". This
## matches prod (display_errors off). Note this means PHP-level notices no
## longer appear on the page — check the container logs for them. MediaWiki's
## own exceptions still render in-page via $wgShowExceptionDetails below.
ini_set('display_errors', '0');
ini_set('log_errors', '1');
$wgDBerrorLog = false;
$wgDebugLogGroups = [];
$wgResourceLoaderDebug = true;
$wgJobRunRate = 0;

## Verbose error output — local debugging.
$wgShowExceptionDetails = true;
$wgShowDBErrorBacktrace = true;
$wgShowSQLErrors = true;
$wgDevelopmentWarnings = true;

## SecureHTML — placeholder. The real prod secret never lives in this repo.
$wgSecureHTMLSecrets = [
	'Wiki admin' => 'dev-local-not-real',
];

## Google Analytics — empty id disables tracking from dev.
$wgGTagAnalyticsId = '';
