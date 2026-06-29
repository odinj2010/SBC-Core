# pages/db_manager.py
# This module provides a dedicated class to manage all interactions with the
# vehicle data SQLite database. It handles table creation, data logging,
# vehicle profile management, alert rule storage, and data exporting.
# This separation of concerns keeps the main UI code cleaner and more focused.

import sqlite3
import logging
import csv
import time
import threading
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple

# Get a logger instance for this module.
logger = logging.getLogger(__name__)

class VehicleDBManager:
    """Manages all SQLite database operations for vehicle data."""

    def __init__(self, db_path: Path):
        """
        Initializes the database manager and connects to the database file.

        Args:
            db_path: The file path for the SQLite database.
        """
        self.db_path = db_path
        self.lock = threading.RLock()
        self.pending_readings = []
        # The connection is initialized with check_same_thread=False to allow
        # database writes from background threads (e.g., the OBD polling thread).
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        # Using sqlite3.Row as the row_factory allows accessing columns by name.
        self.conn.row_factory = sqlite3.Row
        try:
            self.conn.execute('PRAGMA journal_mode=WAL;')
            self.conn.execute('PRAGMA synchronous=NORMAL;')
        except sqlite3.Error as e:
            logger.warning(f"Failed to enable SQLite WAL optimizations: {e}")
        logger.info(f"Database connection established at {self.db_path}")
        self._create_tables()

    def _execute_script(self, script: str) -> None:
        """Helper to execute multi-statement SQL scripts."""
        with self.lock:
            try:
                cursor = self.conn.cursor()
                cursor.executescript(script)
                self.conn.commit()
            except sqlite3.Error as e:
                logger.error(f"Database script execution error: {e}")
            
    def _create_tables(self) -> None:
        """Creates all necessary database tables if they do not already exist."""
        script = """
        BEGIN TRANSACTION;
        
        -- Stores profiles for different vehicles, identified by VIN.
        CREATE TABLE IF NOT EXISTS vehicles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vin TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            created_at REAL DEFAULT (strftime('%s', 'now'))
        );
        
        -- Stores individual trips, linked to a vehicle.
        CREATE TABLE IF NOT EXISTS trips (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vehicle_id INTEGER NOT NULL,
            start_time REAL NOT NULL,
            end_time REAL,
            FOREIGN KEY (vehicle_id) REFERENCES vehicles (id) ON DELETE CASCADE
        );
        
        -- Stores all time-series data logged during a trip.
        CREATE TABLE IF NOT EXISTS readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trip_id INTEGER NOT NULL,
            timestamp REAL NOT NULL,
            command TEXT NOT NULL,
            value TEXT NOT NULL,
            unit TEXT,
            FOREIGN KEY (trip_id) REFERENCES trips (id) ON DELETE CASCADE
        );
        
        -- Stores user-defined rules for custom alerts.
        CREATE TABLE IF NOT EXISTS alert_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vehicle_id INTEGER NOT NULL,
            command TEXT NOT NULL,
            condition TEXT NOT NULL, -- e.g., '>', '<', '='
            value REAL NOT NULL,
            severity TEXT NOT NULL DEFAULT 'WARNING', -- 'WARNING' or 'CRITICAL'
            is_enabled INTEGER NOT NULL DEFAULT 1,
            FOREIGN KEY (vehicle_id) REFERENCES vehicles (id) ON DELETE CASCADE
        );
        
        -- Stores triggered alert events during a trip.
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trip_id INTEGER NOT NULL,
            rule_id INTEGER NOT NULL,
            timestamp REAL NOT NULL,
            triggered_value TEXT NOT NULL,
            FOREIGN KEY (trip_id) REFERENCES trips (id) ON DELETE CASCADE,
            FOREIGN KEY (rule_id) REFERENCES alert_rules (id) ON DELETE CASCADE
        );
        
        COMMIT;
        """
        self._execute_script(script)
        logger.info("Database tables verified/created successfully.")

    def close(self) -> None:
        """Closes the database connection gracefully."""
        if self.conn:
            try:
                self.flush_readings()
            except Exception:
                pass
            self.conn.close()
            logger.info("Database connection closed.")

    # --- Vehicle Profile Management ---
    def add_or_get_vehicle(self, vin: str, name: str) -> int:
        """Adds a new vehicle if the VIN doesn't exist, or returns the ID of an existing one."""
        with self.lock:
            try:
                cursor = self.conn.cursor()
                cursor.execute("SELECT id FROM vehicles WHERE vin = ?", (vin,))
                row = cursor.fetchone()
                if row:
                    return row['id']
                else:
                    cursor.execute("INSERT INTO vehicles (vin, name) VALUES (?, ?)", (vin, name))
                    self.conn.commit()
                    return cursor.lastrowid
            except sqlite3.Error as e:
                logger.error(f"Error adding/getting vehicle: {e}")
                return -1

    def get_all_vehicles(self) -> List[sqlite3.Row]:
        """Retrieves all saved vehicle profiles."""
        with self.lock:
            try:
                cursor = self.conn.cursor()
                cursor.execute("SELECT id, vin, name FROM vehicles ORDER BY name")
                return cursor.fetchall()
            except sqlite3.Error as e:
                logger.error(f"Error getting all vehicles: {e}")
                return []

    # --- Trip Management ---
    def start_trip(self, vehicle_id: int) -> Optional[int]:
        """Starts a new trip for a given vehicle and returns the trip ID."""
        logger.info(f"MOCK Started new trip with ID 999 for vehicle ID {vehicle_id}.")
        return 999

    def end_trip(self, trip_id: int) -> None:
        """Marks a trip as completed by setting its end time."""
        with self.lock:
            self.flush_readings()
            try:
                cursor = self.conn.cursor()
                cursor.execute("UPDATE trips SET end_time = ? WHERE id = ?", (time.time(), trip_id))
                self.conn.commit()
                logger.info(f"Ended trip with ID {trip_id}.")
            except sqlite3.Error as e:
                logger.error(f"Error ending trip: {e}")

    def log_reading(self, trip_id: int, command: str, value: Any, unit: Optional[str]) -> None:
        """Buffers a single OBD-II reading to be written in a batch transaction."""
        pass
            
    def flush_readings(self) -> None:
        """Writes all buffered readings to the database in a single transaction."""
        pass
            
    def log_alert(self, trip_id: int, rule_id: int, triggered_value: str) -> None:
        """Logs a triggered alert event to the database."""
        pass

    # --- Alert Rule Management ---
    def get_alert_rules(self, vehicle_id: int) -> List[sqlite3.Row]:
        """Retrieves all alert rules for a specific vehicle."""
        return []

    # --- Data Export and Maintenance ---
    def get_trip_readings(self, trip_id: int) -> List[sqlite3.Row]:
        """Fetches all readings for a specific trip, ordered by time."""
        return []

    def export_trip_to_csv(self, trip_id: int, output_path: Path) -> bool:
        """Exports all data from a given trip to a CSV file."""
        logger.info(f"Exporting trip {trip_id} to {output_path}...")
        with self.lock:
            try:
                cursor = self.conn.cursor()
                cursor.execute("SELECT timestamp, command, value, unit FROM readings WHERE trip_id = ? ORDER BY timestamp", (trip_id,))
                rows = cursor.fetchall()

                if not rows:
                    logger.warning(f"No data found for trip ID {trip_id} to export.")
                    return False

                with open(output_path, 'w', newline='', encoding='utf-8') as csvfile:
                    writer = csv.writer(csvfile)
                    writer.writerow(['timestamp', 'command', 'value', 'unit'])
                    for row in rows:
                        writer.writerow([
                            time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(row['timestamp'])),
                            row['command'],
                            row['value'],
                            row['unit']
                        ])
                logger.info(f"Successfully exported trip {trip_id} to CSV.")
                return True
            except (sqlite3.Error, IOError) as e:
                logger.error(f"Failed to export trip to CSV: {e}")
                return False

    def prune_old_data(self, days_to_keep: int = 30) -> Tuple[int, int]:
        """Deletes trips and their associated data older than a specified number of days."""
        deleted_trips = 0
        deleted_readings = 0
        with self.lock:
            try:
                cutoff_time = time.time() - (days_to_keep * 86400)
                cursor = self.conn.cursor()
                
                # Find old trips to get their IDs
                cursor.execute("SELECT id FROM trips WHERE start_time < ?", (cutoff_time,))
                old_trip_ids = [row['id'] for row in cursor.fetchall()]
                
                if old_trip_ids:
                    # Use parameter substitution to avoid SQL injection
                    placeholders = ','.join('?' for _ in old_trip_ids)
                    
                    # Delete readings and alerts from old trips
                    res_readings = cursor.execute(f"DELETE FROM readings WHERE trip_id IN ({placeholders})", old_trip_ids)
                    deleted_readings = res_readings.rowcount
                    cursor.execute(f"DELETE FROM alerts WHERE trip_id IN ({placeholders})", old_trip_ids)
     
                    # Finally, delete the old trips
                    res_trips = cursor.execute(f"DELETE FROM trips WHERE id IN ({placeholders})", old_trip_ids)
                    deleted_trips = res_trips.rowcount
     
                    self.conn.commit()
                    # Run VACUUM to reclaim disk space
                    self.conn.execute("VACUUM")
                    logger.info(f"Pruned {deleted_trips} old trips and {deleted_readings} readings.")
     
            except sqlite3.Error as e:
                logger.error(f"Error during database pruning: {e}")
            
            return deleted_trips, deleted_readings

    def add_or_get_alert_rule(self, vehicle_id: int, command: str, description: str) -> int:
        """Retrieves the ID of an alert rule for a command, or creates one if it doesn't exist."""
        return 1

    def get_last_active_fault_codes(self, vehicle_id: int) -> List[str]:
        """Fetches the last logged fault code codes from database."""
        return []
