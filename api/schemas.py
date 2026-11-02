"""Datos admitidos en las peticiones de la API y límites de cada campo."""

from datetime import date, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Login(Body):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=1024)


class PasswordChange(Body):
    current_password: str = Field(min_length=1, max_length=1024)
    new_password: str = Field(min_length=12, max_length=1024)


class SpecialtyRequest(Body):
    specialty: str = Field(min_length=1, max_length=150)
    subspecialty: str | None = Field(default=None, max_length=150)
    prescribed_sessions: int | None = Field(default=None, ge=1, le=1000)


class WaitingRequest(Body):
    patient_id: str = Field(pattern=r"^[0-9]{6}$")
    priority_level: Literal["personal SACYL", "urgente", "preferente", "ordinario"]
    requests: list[SpecialtyRequest] = Field(min_length=1, max_length=20)
    request_date: date
    eligible: bool
    slot_type: Literal["SIMPLE", "DOBLE"]
    time_preference: Literal["MAÑANA", "TARDE"]
    transport_mode: Literal["NORMAL", "AMBULANCIA"]
    preferred_hour: str | None = Field(default=None, max_length=5)
    coordination_rule: Literal["NINGUNA", "MISMO_DIA", "DIAS_ALTERNOS"]
    ai_consent_accepted: bool


class Assignment(Body):
    specialty_filter: str | None = Field(default=None, max_length=150)
    subspecialty_filter: str | None = Field(default=None, max_length=150)
    slot_type_filter: Literal["Todas", "SIMPLE", "DOBLE"] | None = None
    time_preference_filter: Literal["Todas", "MAÑANA", "TARDE"] | None = None
    transport_mode_filter: Literal["Todas", "NORMAL", "AMBULANCIA"] | None = None
    attendance_days: list[str] = Field(min_length=1, max_length=5)


class TreatmentSession(Body):
    session_date_value: date
    session_time_value: time | None = None
    status: Literal[
        "REALIZADA", "REVISION", "FALTA_JUSTIFICADA", "FALTA_NO_JUSTIFICADA"
    ]
    absence_reason: str = Field(default="", max_length=4000)
    out_of_schedule_reason: str = Field(default="", max_length=4000)
    clinical_note: str = Field(default="", max_length=20000)
    pain_eva: int | None = Field(default=None, ge=0, le=10)
    functional_status: str = Field(default="", max_length=4000)
    goal_status: Literal["", "NO_INICIADO", "PARCIAL", "CUMPLIDO", "EMPEORA"] = ""
    incidents: str = Field(default="", max_length=4000)


class Discharge(Body):
    reason: Literal["FIN_TRATAMIENTO", "NO_ASISTE", "DERIVADO", "OTRO"]
    comment: str = Field(default="", max_length=10000)


class Consent(Body):
    accepted: bool


class UserCreate(Body):
    username: str = Field(min_length=1, max_length=100)
    full_name: str = Field(min_length=1, max_length=200)
    dni: str = Field(min_length=9, max_length=9)
    profession: str = Field(min_length=1, max_length=100)
    role: Literal["ADMIN", "CLINICO"]


class SpecialtyCreate(Body):
    name: str = Field(min_length=1, max_length=150)
    requires_subspecialty: bool = False


class AreaCreate(Body):
    specialty_name: str = Field(min_length=1, max_length=150)
    name: str = Field(min_length=1, max_length=150)


class SpecialtyState(Body):
    specialty_name: str = Field(min_length=1, max_length=150)
    active: bool


class AreaState(AreaCreate):
    active: bool


class ProfessionCreate(Body):
    name: str = Field(min_length=1, max_length=100)


class ProfessionState(ProfessionCreate):
    active: bool
