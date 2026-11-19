"""Unified Finding Schema — FAZ B+C."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class Phase(str, Enum):
    PASSIVE  = "passive_recon"
    ACTIVE   = "active_recon"
    VULN     = "vuln_mapping"


class Severity(str, Enum):
    INFO     = "info"
    LOW      = "low"
    MEDIUM   = "medium"
    HIGH     = "high"
    CRITICAL = "critical"


class Finding(BaseModel):
    id:               str       = Field(default_factory=lambda: uuid4().hex[:12])
    target:           str
    timestamp:        str       = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    tool_name:        str
    phase:            Phase
    severity:         Severity  = Severity.INFO
    evidence:         str       = ""
    confidence_score: float     = Field(default=1.0, ge=0.0, le=1.0)
    cve:              Optional[str] = None
    raw_output:       str       = ""
    workspace_id:     str       = ""


class PipelineStatus(str, Enum):
    PENDING   = "pending"
    RUNNING   = "running"
    COMPLETED = "completed"
    FAILED    = "failed"


class PipelineReport(BaseModel):
    pipeline_id:  str
    target:       str
    started_at:   str
    finished_at:  Optional[str] = None
    status:       PipelineStatus
    findings:     list[Finding] = []
    summary:      dict          = Field(default_factory=dict)
    workspace_id: str           = ""
