from pathlib import Path
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase

BASE_DIR = Path(__file__).resolve().parent.parent
DB_DIR = BASE_DIR / "db"
DB_DIR.mkdir(exist_ok=True)
DATABASE_URL = f"sqlite:///{DB_DIR / 'mri_project.db'}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class Base(DeclarativeBase):
    pass

STUDY_OPTIONAL_COLUMNS = {
    "body_region": "VARCHAR(40) DEFAULT 'BRAIN' NOT NULL",
    "study_group": "VARCHAR(80) DEFAULT 'BRAIN_TARGET_TRACKING' NOT NULL",
    "quality_flag": "VARCHAR(80)",
    "comparison_role": "VARCHAR(80)",
    "finding_group": "VARCHAR(80)",
    "diagnosis_alias": "VARCHAR(80) DEFAULT 'PRIVATE_DIAGNOSIS_REDACTED'",
    "sequence_type": "VARCHAR(50)",
    "modality": "VARCHAR(20)",
    "voxel_spacing_x": "FLOAT",
    "voxel_spacing_y": "FLOAT",
    "voxel_spacing_z": "FLOAT",
    "slice_count": "INTEGER",
    "nifti_path": "VARCHAR(255)",
    "mask_path": "VARCHAR(255)",
    "registered_path": "VARCHAR(255)",
    "preprocess_status": "VARCHAR(50)",
    "registration_status": "VARCHAR(50)",
    "segmentation_status": "VARCHAR(50)",
    "is_sample_data": "BOOLEAN DEFAULT 1 NOT NULL",
    "structure_models_json": "TEXT",
    "structure_volumes_json": "TEXT",
}

def ensure_study_optional_columns():
    inspector = inspect(engine)
    if "studies" not in inspector.get_table_names():
        return

    existing = {column["name"] for column in inspector.get_columns("studies")}
    with engine.begin() as conn:
        for column_name, ddl_type in STUDY_OPTIONAL_COLUMNS.items():
            if column_name not in existing:
                conn.execute(text(f"ALTER TABLE studies ADD COLUMN {column_name} {ddl_type}"))

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
