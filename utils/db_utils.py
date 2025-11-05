import pandas as pd
from sqlalchemy.orm import Session
from utils.db_models import get_session, Base
from sqlalchemy import update, select, insert

class DbOps:
    
    def __init__(self):
        self._db_path="sqlite:///data/scheduler.db"
    
    @property
    def db_path(self):
        return self._db_path
    
    # Setter method
    @db_path.setter
    def db_path(self, value):
        if not isinstance(value, str):
            raise ValueError("db_path must be a string!")
        self._db_path = value
        

    def select_records(self, model_class, filters=None, columns=None):
        """
        Generic SELECT function that returns a pandas DataFrame.
        - model_class: SQLAlchemy model class (e.g., Job)
        - filters: dict of column-value pairs for WHERE clause
        - columns: list of column names to return
        """
        session = get_session(self._db_path)
        query = session.query(model_class)

        # Apply filters
        if filters:
            for col, val in filters.items():
                if val and str(val).startswith('~'):
                    # Not equal filter
                    query = query.filter(getattr(model_class, col) != val[1:])
                else:
                    query = query.filter(getattr(model_class, col) == val)

        # Select specific columns
        if columns:
            query = query.with_entities(*[getattr(model_class, c) for c in columns])

        rows = query.all()
        session.close()

        # Convert to DataFrame
        if not rows:
            return pd.DataFrame(columns=columns if columns else [c.name for c in model_class.__table__.columns])
        
        df = pd.DataFrame([r._asdict() if hasattr(r, "_asdict") else r.__dict__ for r in rows])
        df.drop(columns=["_sa_instance_state"], errors="ignore", inplace=True)
        return df


    def insert_record(self, model_class, data):
        """
        Generic INSERT function.
        - model_class: SQLAlchemy model class (e.g., Job)
        - data: dict or list of dicts representing row(s) to insert
        Returns: number of rows inserted
        """
        session = get_session(self._db_path)

        if isinstance(data, dict):
            data = [data]

        objects = [model_class(**row) for row in data]
        session.add_all(objects)
        session.commit()
        count = len(objects)
        session.close()
        return count


    def update_records(self, model_class, filters, updates):
        """
        Generic UPDATE function.
        - model_class: SQLAlchemy model class (e.g., Job)
        - filters: dict of column-value pairs for WHERE clause
        - updates: dict of column-value pairs to update
        Returns: number of rows updated
        """
        session = get_session(self._db_path)
        query = session.query(model_class)

        for col, val in filters.items():
            query = query.filter(getattr(model_class, col) == val)

        count = query.update(updates, synchronize_session=False)
        session.commit()
        session.close()
        return count

    def delete_records(self, model_class, filters):
        """
        Generic DELETE function.
        - model_class: SQLAlchemy model class (e.g., Job)
        - filters: dict of column-value pairs for WHERE clause
        Returns: number of rows deleted
        """
        session = get_session(self._db_path)
        query = session.query(model_class)

        for col, val in filters.items():
            query = query.filter(getattr(model_class, col) == val)

        count = query.delete(synchronize_session=False)
        session.commit()
        session.close()
        return count