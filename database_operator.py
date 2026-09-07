import sqlite3
import os


class AyurvedicAlmanac:

    supported_languages = [
        "Assamese",
        "Bengali",
        "Bodo",
        "Dogri",
        "Gujarati",
        "Hindi",
        "Kannada",
        "Kashmiri",
        "Konkani",
        "Maithili",
        "Malayalam",
        "Manipuri",
        "Marathi",
        "Nepali",
        "Odia",
        "Punjabi",
        "Sanskrit",
        "Santali",
        "Sindhi",
        "Tamil",
        "Telugu",
        "Urdu"
    ]

    def create_database(self) -> None:
        """
        """
        current_dir_path = os.path.dirname(os.path.abspath(__file__))

        with sqlite3.connect(f"{current_dir_path}/AyurvedicDB.db") as conn:

            conn.execute("PRAGMA foreign_keys = ON;")

            cursor = conn.cursor()

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS herbs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                english_name TEXT NOT NULL
            )
            """)

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS illness (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                english_name text not null
            )
            """)

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS treatment (
            FOREIGN KEY (herb_id) REFERENCES herbs (id)
            FOREIGN KEY (illness_id) REFERENCES illness (id)
            )
            """)

    def insert_herb(self, id: int, english_name: str) -> bool:
        current_dir_path = os.path.dirname(os.path.abspath(__file__))
        try:
            with sqlite3.connect(f"{current_dir_path}/AyurvedicDB.db") as conn:
                conn.execute("PRAGMA foreign_keys = ON;")
                cursor = conn.cursor()
                cursor.execute("""
                INSERT INTO Herbs (id,english_name) values (?,?)
                """, (id, english_name))
        except Exception as e:
            return False
        return True

    def insert_illness(self, id: int, english_name: str) -> bool:
        current_dir_path = os.path.dirname(os.path.abspath(__file__))
        try:
            with sqlite3.connect(f"{current_dir_path}/AyurvedicDB.db") as conn:
                conn.execute("PRAGMA foreign_keys = ON;")
                cursor = conn.cursor()
                cursor.execute("""
                INSERT INTO Illness (id,english_name) values (?,?)
                """, (id, english_name))
        except Exception as e:
            return False
        return True


if __name__ == "__main__":
    AyurvedicAlmanac()
