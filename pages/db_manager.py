# pages/db_manager.py
# This module provides a dedicated class to manage all interactions with the
# vehicle data SQLite database. It handles table creation, data logging,
# vehicle profile management, alert rule storage, and data exporting.
# This separation of concerns keeps the main UI code cleaner and more focused.

import sqlite3
import logging
import csv
import time
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
        # The connection is initialized with check_same_thread=False to allow
        # database writes from background threads (e.g., the OBD polling thread).
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        # Using sqlite3.Row as the row_factory allows accessing columns by name.
        self.conn.row_factory = sqlite3.Row
        logger.info(f"Database connection established at {self.db_path}")
        self._create_tables()

    def _execute_script(self, script: str) -> None:
        """Helper to execute multi-statement SQL scripts."""
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
            self.conn.close()
            logger.info("Database connection closed.")

    # --- Vehicle Profile Management ---
    def add_or_get_vehicle(self, vin: str, name: str) -> int:
        """Adds a new vehicle if the VIN doesn't exist, or returns the ID of an existing one."""
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
        try:
            cursor = self.conn.cursor()
            cursor.execute("INSERT INTO trips (vehicle_id, start_time) VALUES (?, ?)", (vehicle_id, time.time()))
            self.conn.commit()
            trip_id = cursor.lastrowid
            logger.info(f"Started new trip with ID {trip_id} for vehicle ID {vehicle_id}.")
            return trip_id
        except sqlite3.Error as e:
            logger.error(f"Error starting trip: {e}")
            return None

    def end_trip(self, trip_id: int) -> None:
        """Marks a trip as completed by setting its end time."""
        try:
            cursor = self.conn.cursor()
            cursor.execute("UPDATE trips SET end_time = ? WHERE id = ?", (time.time(), trip_id))
            self.conn.commit()
            logger.info(f"Ended trip with ID {trip_id}.")
        except sqlite3.Error as e:
            logger.error(f"Error ending trip: {e}")

    # --- Data and Alert Logging ---
    def log_reading(self, trip_id: int, command: str, value: Any, unit: Optional[str]) -> None:
        """Logs a single OBD-II reading to the database."""
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                "INSERT INTO readings (trip_id, timestamp, command, value, unit) VALUES (?, ?, ?, ?, ?)",
                (trip_id, time.time(), command, str(value), unit)
            )
            self.conn.commit()
        except sqlite3.Error as e:
            # Avoid flooding logs for this common operation.
            # logger.debug(f"Error logging reading: {e}")
            pass
            
    def log_alert(self, trip_id: int, rule_id: int, triggered_value: str) -> None:
        """Logs a triggered alert event to the database."""
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                "INSERT INTO alerts (trip_id, rule_id, timestamp, triggered_value) VALUES (?, ?, ?, ?)",
                (trip_id, rule_id, time.time(), triggered_value)
            )
            self.conn.commit()
            logger.info(f"Logged alert for rule ID {rule_id} with value {triggered_value}.")
        except sqlite3.Error as e:
            logger.error(f"Error logging alert: {e}")

    # --- Alert Rule Management ---
    def get_alert_rules(self, vehicle_id: int) -> List[sqlite3.Row]:
        """Retrieves all alert rules for a specific vehicle."""
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM alert_rules WHERE vehicle_id = ? AND is_enabled = 1 ORDER BY command", (vehicle_id,))
            return cursor.fetchall()
        except sqlite3.Error as e:
            logger.error(f"Error fetching alert rules: {e}")
            return []

    # --- Data Export and Maintenance ---
    def get_trip_readings(self, trip_id: int) -> List[sqlite3.Row]:
        """Fetches all readings for a specific trip, ordered by time."""
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT timestamp, command, value, unit FROM readings WHERE trip_id = ? ORDER BY timestamp DESC LIMIT 200", (trip_id,))
            return cursor.fetchall()
        except sqlite3.Error as e:
            logger.error(f"Error getting trip readings: {e}")
            return []

    def export_trip_to_csv(self, trip_id: int, output_path: Path) -> bool:
        """Exports all data from a given trip to a CSV file."""
        logger.info(f"Exporting trip {trip_id} to {output_path}...")
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
