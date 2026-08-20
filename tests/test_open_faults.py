from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.database import get_open_faults
from src.main import build_fault_from_database


database_faults = get_open_faults(10)

pulse_faults = [
    build_fault_from_database(fault)
    for fault in database_faults
]

print(pulse_faults)