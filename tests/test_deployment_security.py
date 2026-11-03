"""Production settings and Firebase credentials fail closed before serving data."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from backend.core.config import Settings, settings
from backend.core.firebase import initialize_firebase


def production_settings(**changes):
    value = Settings()
    value.APP_ENV = "production"
    value.ALLOWED_HOSTS = ["api.example.test"]
    value.GEMINI_PAID_SERVICES_CONFIRMED = True
    value.GEMINI_NONPERSONAL_TESTING_CONFIRMED = False
    for key, item in changes.items():
        setattr(value, key, item)
    return value


def test_production_requires_confirmation_of_provider_data_terms():
    with pytest.raises(ValueError, match="data terms for the selected provider"):
        production_settings(GEMINI_PAID_SERVICES_CONFIRMED=False).validate_deployment()


@pytest.mark.parametrize("hosts", [[], ["*"], ["*.example.test"], ["https://api.example.test"],
                                    ["api.example.test:8000"], ["user@api.example.test"]])
def test_production_rejects_missing_or_ambiguous_host_restrictions(hosts):
    with pytest.raises(ValueError, match="ALLOWED_HOSTS"):
        production_settings(ALLOWED_HOSTS=hosts).validate_deployment()


def test_explicit_production_settings_are_accepted():
    production_settings().validate_deployment()


def test_production_accepts_confirmed_nonpersonal_testing_without_paid_confirmation():
    production_settings(GEMINI_PAID_SERVICES_CONFIRMED=False,
                        GEMINI_NONPERSONAL_TESTING_CONFIRMED=True).validate_deployment()


@pytest.mark.parametrize("hosts", [[], ["*"], ["https://api.example.test"]])
def test_nonpersonal_testing_still_requires_production_host_restrictions(hosts):
    with pytest.raises(ValueError, match="ALLOWED_HOSTS"):
        production_settings(GEMINI_PAID_SERVICES_CONFIRMED=False,
                            GEMINI_NONPERSONAL_TESTING_CONFIRMED=True,
                            ALLOWED_HOSTS=hosts).validate_deployment()


def test_development_remains_available_without_paid_service_confirmation():
    value = production_settings(APP_ENV="development", ALLOWED_HOSTS=[],
                                GEMINI_PAID_SERVICES_CONFIRMED=False)
    value.validate_deployment()
    value.APP_ENV = "prodution"
    with pytest.raises(ValueError, match="APP_ENV"):
        value.validate_deployment()


@pytest.mark.asyncio
async def test_invalid_production_configuration_stops_before_firebase_initialization(monkeypatch):
    from backend.main import app, lifespan

    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "ALLOWED_HOSTS", ["api.example.test"])
    monkeypatch.setattr(settings, "GEMINI_PAID_SERVICES_CONFIRMED", False)
    monkeypatch.setattr(settings, "GEMINI_NONPERSONAL_TESTING_CONFIRMED", False)
    initialize = Mock()
    monkeypatch.setattr("backend.main.initialize_firebase", initialize)
    with pytest.raises(ValueError, match="data terms for the selected provider"):
        async with lifespan(app):
            pytest.fail("Invalid production settings must not start the server.")
    initialize.assert_not_called()


@pytest.fixture
def firebase_setup(monkeypatch):
    monkeypatch.setattr(settings, "FIREBASE_PROJECT_ID", "test-project")
    monkeypatch.setattr(settings, "FIREBASE_USE_ADC", False)
    monkeypatch.setenv("FIREBASE_ADMIN_KEY_PATH", ".secrets/example.json")
    monkeypatch.delenv("FIREBASE_AUTH_EMULATOR_HOST", raising=False)
    monkeypatch.delenv("FIRESTORE_EMULATOR_HOST", raising=False)
    certificate = Mock(return_value=SimpleNamespace(project_id="test-project"))
    default = Mock(return_value=SimpleNamespace(project_id="test-project"))
    initialize = Mock()
    monkeypatch.setattr("backend.core.firebase.credentials.Certificate", certificate)
    monkeypatch.setattr("backend.core.firebase.credentials.ApplicationDefault", default)
    monkeypatch.setattr("backend.core.firebase.firebase_admin.initialize_app", initialize)
    return certificate, default, initialize


def test_existing_local_key_configuration_is_retained(firebase_setup):
    certificate, default, initialize = firebase_setup
    initialize_firebase()
    certificate.assert_called_once()
    default.assert_not_called()
    assert initialize.call_args.kwargs["options"]["projectId"] == "test-project"


def test_managed_credentials_do_not_load_a_private_key_file(firebase_setup, monkeypatch):
    certificate, default, initialize = firebase_setup
    monkeypatch.setattr(settings, "FIREBASE_USE_ADC", True)
    monkeypatch.delenv("FIREBASE_ADMIN_KEY_PATH")
    initialize_firebase()
    certificate.assert_not_called()
    default.assert_called_once()
    initialize.assert_called_once()


def test_ambiguous_credentials_are_rejected(firebase_setup, monkeypatch):
    monkeypatch.setattr(settings, "FIREBASE_USE_ADC", True)
    with pytest.raises(RuntimeError, match="Unset FIREBASE_ADMIN_KEY_PATH"):
        initialize_firebase()
    firebase_setup[2].assert_not_called()


@pytest.mark.parametrize("variable", ["FIREBASE_AUTH_EMULATOR_HOST", "FIRESTORE_EMULATOR_HOST"])
def test_live_backend_rejects_emulator_routing(firebase_setup, monkeypatch, variable):
    monkeypatch.setenv(variable, "localhost:9099")
    with pytest.raises(RuntimeError, match="live Firebase"):
        initialize_firebase()
    firebase_setup[2].assert_not_called()


def test_credentials_from_a_different_project_are_rejected(firebase_setup):
    firebase_setup[0].return_value.project_id = "different-project"
    with pytest.raises(RuntimeError, match="do not match"):
        initialize_firebase()
    firebase_setup[2].assert_not_called()
