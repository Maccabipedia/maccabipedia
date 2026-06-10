<?php

/**
 * (Re)create every Cargo table declared by an imported template — in ONE
 * PHP process.
 *
 * Why not cargoRecreateData.php in a loop: each invocation pays ~1s of
 * MediaWiki CLI bootstrap for milliseconds of actual DDL, so 64 tables cost
 * over a minute of pure overhead. This script does the same creation calls
 * in a single bootstrap. It does NOT populate the tables — that's
 * populateLocalCargoData.php (run by recreate-cargo-tables.sh after this).
 *
 * Runs inside the mediawiki container, copied next to core's maintenance
 * scripts by recreate-cargo-tables.sh:
 *   php maintenance/createLocalCargoTables.php [--tables A,B,...]
 */

if ( getenv( 'MW_INSTALL_PATH' ) ) {
	require_once getenv( 'MW_INSTALL_PATH' ) . '/maintenance/Maintenance.php';
} else {
	require_once __DIR__ . '/Maintenance.php';
}

$maintClass = CreateLocalCargoTables::class;

class CreateLocalCargoTables extends Maintenance {

	public function __construct() {
		parent::__construct();
		$this->requireExtension( 'Cargo' );
		$this->addDescription( 'Recreate the DB tables for every declared Cargo table in one process.' );
		$this->addOption( 'tables', 'Comma-separated subset of Cargo tables to recreate', false, true );
	}

	public function execute() {
		$declaredTables = array_keys( CargoUtils::getAllPageProps( 'CargoTableName' ) );
		sort( $declaredTables );
		if ( $this->hasOption( 'tables' ) ) {
			$declaredTables = array_map( 'trim', explode( ',', $this->getOption( 'tables' ) ) );
		}
		if ( !$declaredTables ) {
			$this->fatalError( 'no Cargo tables are declared locally — import the declaration templates first' );
		}

		$user = User::newSystemUser( 'Maintenance script', [ 'steal' => true ] );
		$created = 0;
		foreach ( $declaredTables as $tableName ) {
			$templatePageID = CargoUtils::getTemplateIDForDBTable( $tableName );
			if ( $templatePageID == null ) {
				$this->output( "    - $tableName — SKIP: not declared in any template\n" );
				continue;
			}
			CargoUtils::recreateDBTablesForTemplate( $templatePageID, false, $user, $tableName );
			$this->output( "    - $tableName\n" );
			$created++;
		}
		$this->output( "done — $created Cargo table(s) created.\n" );
	}

}

require_once RUN_MAINTENANCE_IF_MAIN;
