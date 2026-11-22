import sqlite3
import time
from pathlib import Path

DB = Path(__file__).parent / "data" / "learning.db"
DB.parent.mkdir(exist_ok=True)


class Learner:
    def __init__(self):
        self.db = sqlite3.connect(DB)

        self.db.execute("""
            CREATE TABLE IF NOT EXISTS observations (
                id INTEGER PRIMARY KEY,
                board_hash TEXT,
                rule TEXT,
                predicted TEXT,
                actual TEXT,
                success INTEGER,
                created REAL
            )
        """)

        columns = {
            row[1]
            for row in self.db.execute(
                "PRAGMA table_info(observations)"
            )
        }

        if "source" not in columns:
            self.db.execute("""
                ALTER TABLE observations
                ADD COLUMN source TEXT NOT NULL DEFAULT 'legacy'
            """)

        # Identify the two known artificial test records.
        self.db.execute("""
            UPDATE observations
            SET source = 'test'
            WHERE board_hash = 'test-board'
              AND rule = 'shooting'
              AND predicted = 'red-pixel-1'
              AND actual = 'red-pixel-2'
              AND success = 0
        """)

        self.db.commit()

    def record(
        self,
        board_hash,
        rule,
        predicted,
        actual,
        source="gameplay"
    ):
        allowed_sources = {"gameplay", "test"}

        if source not in allowed_sources:
            raise ValueError("Invalid observation source")

        success = int(predicted == actual)

        self.db.execute("""
            INSERT INTO observations
            (board_hash, rule, predicted, actual,
             success, created, source)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            board_hash,
            rule,
            predicted,
            actual,
            success,
            time.time(),
            source
        ))

        self.db.commit()
        return success

    def confidence(self, rule):
        row = self.db.execute("""
            SELECT COUNT(*), COALESCE(SUM(success), 0)
            FROM observations
            WHERE rule = ?
              AND source = 'gameplay'
        """, (rule,)).fetchone()

        total, correct = row
        return correct / total if total else 0.0

    def history(self, limit=10):
        return self.db.execute("""
            SELECT rule, predicted, actual, success
            FROM observations
            WHERE source = 'gameplay'
            ORDER BY id DESC
            LIMIT ?
        """, (limit,)).fetchall()

    def source_counts(self):
        return self.db.execute("""
            SELECT source, COUNT(*)
            FROM observations
            GROUP BY source
            ORDER BY source
        """).fetchall()

    def close(self):
        self.db.close()


if __name__ == "__main__":
    ai = Learner()

    print("LEARNING ENGINE — READ-ONLY DIAGNOSTIC")
    print("Source counts:", ai.source_counts())
    print("Gameplay shooting confidence:",
          ai.confidence("shooting"))
    print("Gameplay observations:", ai.history())

    ai.close()
