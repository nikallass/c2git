from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional
from master.models import Job

@dataclass
class Session:
    id: str                # Branch name md5(hostname)[:10]
    hostname: str          # Encrypted hostname
    last_seen: datetime    # Last activity
    status: str            # active/inactive
    jobs: List[Job]        # Job history
    
    @property
    def is_active(self) -> bool:
        """Check if session is currently active based on last_seen"""
        time_diff = (datetime.now() - self.last_seen).total_seconds()
        return time_diff < 180  # 3 minutes, matching scan_for_sessions threshold
