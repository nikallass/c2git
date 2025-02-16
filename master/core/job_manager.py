import asyncio
import os
import uuid
from datetime import datetime
from typing import List, Optional, Dict
from master.models import Job, TaskStatus
from .session_manager import SessionManager

class JobManager:
    def __init__(self, session_manager: SessionManager):
        self.session_manager = session_manager
        self.jobs: Dict[str, Job] = {}
        self._running = False
        self.job_refresh_rate = self.session_manager.git_handler.config.job_refresh_rate
        self.max_retries = self.session_manager.git_handler.config.job_retry_count
        self.retry_delay = self.session_manager.git_handler.config.job_retry_delay
        # Track jobs per session to manage queue
        self.session_queues: Dict[str, List[str]] = {}  # session_id -> [job_ids]

    async def create_job(self, command: str, targets: List[str]) -> Job:
        """Creates new job"""
        job = Job(
            id=str(uuid.uuid4()),
            command=command,
            targets=targets,
            created_at=datetime.now()
        )
        self.jobs[job.id] = job
        
        # Add job to session queues and create monitoring tasks
        for target in targets:
            if target not in self.session_queues:
                self.session_queues[target] = []
            self.session_queues[target].append(job.id)
            
            # Set initial status to in_queue if not first job
            if len(self.session_queues[target]) > 1:
                job.task_statuses[target] = TaskStatus.in_queue
            
            asyncio.create_task(self._monitor_session(job, target))
        
        return job

    async def get_job(self, job_id: str) -> Optional[Job]:
        """Get job by ID"""
        return self.jobs.get(job_id)

    async def get_jobs(self) -> List[Job]:
        """Get all jobs"""
        return list(self.jobs.values())

    async def start(self):
        """Start job processing"""
        self._running = True
        while self._running:
            await asyncio.sleep(1)

    async def stop(self):
        """Stop job processing"""
        self._running = False
        # Wait for any pending tasks to complete
        tasks = [task for task in asyncio.all_tasks() 
                if task is not asyncio.current_task()]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _monitor_session(self, job: Job, target: str):
        """Monitor and process a single session for a job"""
        while self._running:
            try:
                # Get session state
                session = await self.session_manager.get_session(target)
                if not session:
                    job.task_statuses[target] = TaskStatus.failed
                    job.results[target] = "Failed: Session not found"
                    self._cleanup_job(job.id, target)
                    return

                # Update repository files
                self.session_manager.git_handler._init_repository()

                # Only process if this job is first in queue
                if target not in job.sent_to_sessions:
                    if self.session_queues[target][0] != job.id:
                        job.task_statuses[target] = TaskStatus.in_queue
                        await asyncio.sleep(self.job_refresh_rate)
                        continue
                        
                    job.task_statuses[target] = TaskStatus.waiting_execution
                    
                    # Wait for state to become 2 or be empty
                    max_retries = 30  # 30 seconds timeout
                    for _ in range(max_retries):
                        state_file = os.path.join(self.session_manager.git_handler.config.local_repo_path, "state")
                        if os.path.exists(state_file):
                            with open(state_file, "r") as f:
                                state = f.read().strip()
                                if state == "2" or not state:
                                    # Send command
                                    success = await self.session_manager.send_command(target, job.command)
                                    if success:
                                        job.sent_to_sessions.append(target)
                                        break
                        await asyncio.sleep(1)
                    else:
                        job.task_statuses[target] = TaskStatus.failed
                        job.results[target] = "Failed: State timeout"
                        return

                    job.sent_to_sessions.append(target)

                    # Wait for response with timeout
                    start_time = datetime.now()
                    while (datetime.now() - start_time).seconds < self.session_manager.git_handler.config.command_timeout:
                        response = await self.session_manager.get_response(target)
                        if response:
                            job.results[target] = response
                            job.task_statuses[target] = TaskStatus.executed
                            self._cleanup_job(job.id, target)
                            return
                        await asyncio.sleep(1)

                    job.task_statuses[target] = TaskStatus.failed
                    job.results[target] = "Failed: Response timeout"
                    return

            except Exception as e:
                job.task_statuses[target] = TaskStatus.failed
                job.results[target] = f"Failed: {str(e)}"
                return

            await asyncio.sleep(self.job_refresh_rate)
            
    def _cleanup_job(self, job_id: str, target: str):
        """Remove completed/failed job from session queue"""
        if target in self.session_queues and job_id in self.session_queues[target]:
            self.session_queues[target].remove(job_id)
