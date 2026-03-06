import mysql.connector
from mysql.connector import Error


def get_connection():
    """
    Creates and returns a MySQL database connection.
    Raises error if connection fails.
    """

    try:
        connection = mysql.connector.connect(
            host="localhost",
            user="root",
            password="root",
            database="smart_blood_bank"
        )

        if connection.is_connected():
            return connection

    except Error as e:
        print("Database Connection Error:", e)
        raise