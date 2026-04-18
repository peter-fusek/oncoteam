"""Tests for #394 geographic enrollment policy — haversine, scoring, filter."""

from __future__ import annotations

import pytest

from oncoteam.eligibility import (
    default_enrollment_preference,
    geographic_score,
    haversine,
    is_geographically_accessible,
)
from oncoteam.models import EnrollmentPreference, HomeRegion, PatientProfile, TrialSite

# Well-known reference points
_BRATISLAVA = (48.1486, 17.1077)
_VIENNA = (48.2082, 16.3738)  # ~60 km from Bratislava
_PRAGUE = (50.0755, 14.4378)  # ~330 km
_BERLIN = (52.5200, 13.4050)  # ~555 km
_MADRID = (40.4168, -3.7038)  # ~1750 km
_HOUSTON = (29.7604, -95.3698)  # ~8800 km


def _bratislava_patient(
    max_travel_km: int = 600,
    allow_global: bool = False,
    excluded: list[str] | None = None,
) -> PatientProfile:
    return PatientProfile(
        patient_id="test-q1b",
        name="Test Erika",
        diagnosis_code="C18.7",
        diagnosis_description="test",
        tumor_site="sigmoid",
        treatment_regimen="FOLFOX",
        home_region=HomeRegion(
            city="Bratislava", country="SK", lat=_BRATISLAVA[0], lon=_BRATISLAVA[1]
        ),
        enrollment_preference=EnrollmentPreference(
            max_travel_km=max_travel_km,
            preferred_countries=["SK", "CZ", "AT", "HU", "PL", "DE", "CH"],
            language_preferences=["sk", "cs", "en"],
            excluded_countries=excluded or [],
            allow_unique_opportunity_global=allow_global,
        ),
    )


class TestHaversine:
    def test_same_point_is_zero(self):
        assert haversine(*_BRATISLAVA, *_BRATISLAVA) == pytest.approx(0.0, abs=1e-6)

    def test_bratislava_to_vienna_roughly_60km(self):
        km = haversine(*_BRATISLAVA, *_VIENNA)
        assert 50 < km < 70

    def test_bratislava_to_prague_roughly_290km_great_circle(self):
        # Great-circle distance is ~290 km; road distance is ~330 km.
        km = haversine(*_BRATISLAVA, *_PRAGUE)
        assert 270 < km < 310

    def test_bratislava_to_houston_transatlantic(self):
        km = haversine(*_BRATISLAVA, *_HOUSTON)
        assert 8500 < km < 9200

    def test_symmetric(self):
        a = haversine(*_BRATISLAVA, *_VIENNA)
        b = haversine(*_VIENNA, *_BRATISLAVA)
        assert a == pytest.approx(b)


class TestDefaultEnrollmentPreference:
    def test_sk_home_seeds_neighbors(self):
        pref = default_enrollment_preference("SK")
        assert pref.preferred_countries[0] == "SK"
        for neighbor in ("CZ", "AT", "HU", "PL"):
            assert neighbor in pref.preferred_countries

    def test_case_insensitive(self):
        pref = default_enrollment_preference("sk")
        assert pref.preferred_countries[0] == "SK"

    def test_unknown_country_just_home(self):
        pref = default_enrollment_preference("ZZ")
        assert pref.preferred_countries == ["ZZ"]

    def test_default_max_travel(self):
        pref = default_enrollment_preference("SK")
        assert pref.max_travel_km == 600

    def test_override_max_travel(self):
        pref = default_enrollment_preference("SK", max_travel_km=1500)
        assert pref.max_travel_km == 1500

    def test_language_override(self):
        pref = default_enrollment_preference("SK", language_preferences=["sk", "cs", "en"])
        assert pref.language_preferences == ["sk", "cs", "en"]

    def test_global_opt_in_off_by_default(self):
        pref = default_enrollment_preference("SK")
        assert pref.allow_unique_opportunity_global is False


class TestGeographicScore:
    def test_empty_sites_returns_zero(self):
        patient = _bratislava_patient()
        assert geographic_score([], patient) == 0.0

    def test_no_home_region_returns_neutral(self):
        patient = PatientProfile(
            patient_id="test",
            name="N",
            diagnosis_code="C18",
            diagnosis_description="",
            tumor_site="",
            treatment_regimen="",
        )
        sites = [TrialSite(country="US", city="Houston", status="recruiting")]
        # Backwards-compatible: no prefs = neutral, not filtered
        assert geographic_score(sites, patient) == 50.0

    def test_home_country_scores_highest(self):
        patient = _bratislava_patient()
        sk_site = TrialSite(
            country="SK", city="Bratislava", status="recruiting", lat=48.1486, lon=17.1077
        )
        de_site = TrialSite(
            country="DE", city="Berlin", status="recruiting", lat=_BERLIN[0], lon=_BERLIN[1]
        )
        sk_score = geographic_score([sk_site], patient)
        de_score = geographic_score([de_site], patient)
        assert sk_score > de_score
        assert sk_score == pytest.approx(100.0)

    def test_best_site_wins(self):
        patient = _bratislava_patient()
        sites = [
            TrialSite(country="DE", city="Berlin", status="recruiting"),
            TrialSite(country="SK", city="Bratislava", status="recruiting"),
        ]
        # SK site should drive the score even when listed second
        assert geographic_score(sites, patient) == 100.0

    def test_inactive_site_filtered(self):
        patient = _bratislava_patient()
        sk_completed = TrialSite(
            country="SK", city="Bratislava", status="completed", lat=48.1486, lon=17.1077
        )
        cz_recruiting = TrialSite(
            country="CZ", city="Prague", status="recruiting", lat=_PRAGUE[0], lon=_PRAGUE[1]
        )
        # Completed SK site is filtered, fall back to CZ
        score = geographic_score([sk_completed, cz_recruiting], patient)
        assert 0.0 < score < 100.0

    def test_non_preferred_country_filtered_without_global_opt_in(self):
        patient = _bratislava_patient(allow_global=False)
        us_site = TrialSite(country="US", city="Houston", status="recruiting")
        assert geographic_score([us_site], patient) == 0.0

    def test_non_preferred_country_allowed_with_global_opt_in(self):
        patient = _bratislava_patient(allow_global=True)
        us_site = TrialSite(country="US", city="Houston", status="recruiting")
        score = geographic_score([us_site], patient)
        # Allowed, but scores low (worst tier)
        assert score > 0.0
        assert score < 50.0

    def test_excluded_country_filtered(self):
        patient = _bratislava_patient(excluded=["DE"])
        de_site = TrialSite(
            country="DE", city="Berlin", status="recruiting", lat=_BERLIN[0], lon=_BERLIN[1]
        )
        assert geographic_score([de_site], patient) == 0.0

    def test_distance_penalty_reduces_score(self):
        patient = _bratislava_patient()
        near_at = TrialSite(
            country="AT", city="Vienna", status="recruiting", lat=_VIENNA[0], lon=_VIENNA[1]
        )
        far_de = TrialSite(
            country="DE", city="Berlin", status="recruiting", lat=_BERLIN[0], lon=_BERLIN[1]
        )
        assert geographic_score([near_at], patient) > geographic_score([far_de], patient)

    def test_over_max_travel_filtered_for_distant_tier(self):
        # Tier > 1 (not home/immediate neighbor) and beyond max_travel_km → filtered
        patient = _bratislava_patient(max_travel_km=400)
        de_far = TrialSite(
            country="DE",
            city="Berlin",
            status="recruiting",
            lat=_BERLIN[0],
            lon=_BERLIN[1],
        )
        assert geographic_score([de_far], patient) == 0.0

    def test_preferred_neighbor_passes_even_when_over_max_travel(self):
        # CZ is immediate neighbor (tier 1) — should not be hard-filtered by distance alone.
        patient = _bratislava_patient(max_travel_km=200)
        cz = TrialSite(
            country="CZ", city="Prague", status="recruiting", lat=_PRAGUE[0], lon=_PRAGUE[1]
        )
        assert geographic_score([cz], patient) > 0.0

    def test_site_without_coords_uses_country_tier(self):
        patient = _bratislava_patient()
        at_no_coords = TrialSite(country="AT", city="Vienna", status="recruiting")
        score = geographic_score([at_no_coords], patient)
        # T2 (AT is index 2 in [SK, CZ, AT, ...]), no distance penalty → 100 - 2*12 = 76
        assert score == pytest.approx(76.0)


class TestIsGeographicallyAccessible:
    def test_home_country_accessible(self):
        patient = _bratislava_patient()
        sk = TrialSite(country="SK", city="Bratislava", status="recruiting")
        assert is_geographically_accessible([sk], patient)

    def test_us_site_not_accessible(self):
        patient = _bratislava_patient(allow_global=False)
        us = TrialSite(country="US", city="Houston", status="recruiting")
        assert not is_geographically_accessible([us], patient)

    def test_us_site_accessible_with_global_opt_in(self):
        patient = _bratislava_patient(allow_global=True)
        us = TrialSite(country="US", city="Houston", status="recruiting")
        assert is_geographically_accessible([us], patient)

    def test_no_sites_not_accessible(self):
        patient = _bratislava_patient()
        assert not is_geographically_accessible([], patient)


class TestSeededPatientsHaveBratislavaHome:
    """Regression: q1b, e5g, sgu should ship with Bratislava HomeRegion + prefs."""

    def test_q1b_has_bratislava_home(self):
        from oncoteam.patient_context import PATIENT

        assert PATIENT.home_region is not None
        assert PATIENT.home_region.city == "Bratislava"
        assert PATIENT.home_region.country == "SK"
        assert PATIENT.enrollment_preference is not None
        assert PATIENT.enrollment_preference.preferred_countries[0] == "SK"

    def test_e5g_has_bratislava_home(self):
        from oncoteam.patient_context import PATIENT_E5G

        assert PATIENT_E5G.home_region is not None
        assert PATIENT_E5G.home_region.city == "Bratislava"
        assert PATIENT_E5G.enrollment_preference is not None

    def test_sgu_has_bratislava_home(self):
        from oncoteam.patient_context import PATIENT_SGU

        assert PATIENT_SGU.home_region is not None
        assert PATIENT_SGU.home_region.city == "Bratislava"
        assert PATIENT_SGU.enrollment_preference is not None
