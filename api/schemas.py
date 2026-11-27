"""Datos admitidos en las peticiones de la API y límites de cada campo."""

from datetime import date, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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
    initial_note: str = Field(default="", max_length=10000)


class WaitingRequest(Body):
    patient_id: str = Field(pattern=r"^[0-9]{6}$")
    priority_level: Literal["personal SACYL", "urgente", "preferente", "ordinario"]
    requests: list[SpecialtyRequest] = Field(min_length=1, max_length=20)
    request_date: date
    eligible: bool
    slot_type: Literal["SIMPLE", "DOBLE"]
    time_preference: Literal["MAÑANA", "TARDE"] | None = None
    transport_mode: Literal["NORMAL", "AMBULANCIA"]
    preferred_hour: str | None = Field(default=None, max_length=5)
    coordination_rule: Literal["NINGUNA", "MISMO_DIA", "DIAS_ALTERNOS"]
    ai_consent_accepted: bool | None = None
    confirm_duplicate: bool = Field(default=False, strict=True)

    @field_validator("time_preference", mode="before")
    @classmethod
    def empty_shift(cls, value):
        return None if value == "" else value

    @model_validator(mode="after")
    def ambulance_shift(self):
        if self.transport_mode == "AMBULANCIA" and self.time_preference is None:
            self.time_preference = "MAÑANA"
        return self


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
    knee_flexion_deg: float | None = Field(default=None, ge=0, le=180)
    knee_extension_deficit_deg: float | None = Field(default=None, ge=0, le=180)
    tug_seconds: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    tug_conditions: str | None = Field(default=None, max_length=100)
    koos_jr_raw: int | None = Field(default=None, ge=0, le=28)
    knee_goal_metric: Literal["knee_flexion_deg", "knee_extension_deficit_deg"] | None = None
    knee_goal_target: float | None = Field(default=None, ge=0, le=180)

    @model_validator(mode="after")
    def validate_knee_measurements(self):
        self.tug_conditions = (self.tug_conditions or "").strip() or None
        if (self.tug_seconds is None) != (self.tug_conditions is None):
            raise ValueError("Registra el tiempo del TUG y sus condiciones de medición.")
        if (self.knee_goal_metric is None) != (self.knee_goal_target is None):
            raise ValueError("Selecciona la medida del objetivo e introduce su valor.")
        if self.status not in {"REALIZADA", "REVISION"} and any(
            value is not None for value in (
                self.knee_flexion_deg, self.knee_extension_deficit_deg,
                self.tug_seconds, self.koos_jr_raw, self.knee_goal_metric,
            )
        ):
            raise ValueError("Las medidas y metas solo se registran en sesiones realizadas o revisiones.")
        return self


class Discharge(Body):
    reason: Literal["FIN_TRATAMIENTO", "NO_ASISTE", "DERIVADO", "OTRO"]
    comment: str = Field(default="", max_length=10000)


class Consent(Body):
    accepted: bool
    evidence_reference: str | None = Field(
        default=None, max_length=80, pattern=r"^[A-Za-z0-9][A-Za-z0-9._/-]*$"
    )


class UserCreate(Body):
    username: str = Field(min_length=1, max_length=100)
    full_name: str = Field(min_length=1, max_length=200)
    dni: str = Field(min_length=9, max_length=9)
    profession: str = Field(min_length=1, max_length=100)
    role: Literal["ADMIN", "CLINICO", "MEDICO"]


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


class ClinicianLeave(Body):
    on_leave: bool = Field(strict=True)


class TreatmentReassignment(Body):
    expected_clinician_dni: str = Field(pattern=r"^[0-9]{8}[A-Z]$")
    target_user_id: int = Field(ge=1)


class AISummaryRequest(Body):
    synthetic_data_confirmed: bool = False
