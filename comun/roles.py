"""Roles de acceso y correspondencia con las profesiones del catálogo."""

ROLE_LABELS = {"ADMIN": "Administrador", "CLINICO": "Clínico", "MEDICO": "Médico"}
MEDICAL_PROFESSION = "Médico rehabilitador"


def role_for_profession(profession):
    if profession == "Administrador":
        return "ADMIN"
    if profession == MEDICAL_PROFESSION:
        return "MEDICO"
    return "CLINICO"


def can_use_ai_summary(user):
    """La administración de cuentas no concede acceso a los resúmenes."""
    return user.get("role") == "MEDICO" and user.get("profession") == MEDICAL_PROFESSION


def can_create_request(user):
    """La solicitud inicial corresponde al médico o al administrador."""
    return user.get("role") == "ADMIN" or can_use_ai_summary(user)
