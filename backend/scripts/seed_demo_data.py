"""Seed three demo businesses with realistic test data.

Creates:
- 3 businesses (Dhaka Dental, Quick HVAC, Rahman Law)
- 1 BusinessSetting row per business (defaults)
- 1 business_admin User per business
- 5 Services per business (industry-appropriate)
- 7 OperatingHours rows per business (Mon-Sat 9am-6pm, Sun closed)
- 10 FAQs per business

Idempotent: re-running detects existing businesses by slug and skips them.

Run from ``backend/``:

    .venv\\Scripts\\python scripts\\seed_demo_data.py

All demo admin passwords are ``demo1234``. This is intentional — these are
throwaway demo accounts. Production accounts are created via the public
``/auth/register`` endpoint with real passwords, not this script.
"""

from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass, field
from datetime import time
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_factory, engine
from app.core.security import hash_password
from app.models.business import Business
from app.models.business_setting import BusinessSetting
from app.models.enums import BusinessStatus, DayOfWeek, UserRole
from app.models.faq import Faq
from app.models.operating_hours import OperatingHours
from app.models.service import Service
from app.models.user import User


_DEMO_PASSWORD = "demo1234"


# ---------------------------------------------------------------------------
# Demo data definitions
# ---------------------------------------------------------------------------

@dataclass
class DemoService:
    name: str
    description: str
    duration_minutes: int
    price: Decimal
    display_order: int = 0
    buffer_minutes: int = 0


@dataclass
class DemoFaq:
    question: str
    answer: str
    category: str
    display_order: int = 0


@dataclass
class DemoBusiness:
    slug: str
    name: str
    industry: str
    timezone_name: str
    admin_email: str
    admin_full_name: str
    services: list[DemoService] = field(default_factory=list)
    faqs: list[DemoFaq] = field(default_factory=list)


DHAKA_DENTAL = DemoBusiness(
    slug="dhaka-dental",
    name="Dhaka Dental Clinic",
    industry="dental",
    timezone_name="Asia/Dhaka",
    admin_email="owner@dhakadental.com",
    admin_full_name="Dr. Rahman",
    services=[
        DemoService("Routine Cleaning", "Standard dental cleaning and polish, 45 minutes.", 45, Decimal("1500.00"), 1),
        DemoService("Dental Filling", "Composite filling for small to medium cavities.", 60, Decimal("3500.00"), 2),
        DemoService("Tooth Extraction", "Simple extraction, includes local anesthesia.", 45, Decimal("4500.00"), 3),
        DemoService("Root Canal", "Single-tooth root canal therapy.", 90, Decimal("12000.00"), 4),
        DemoService("Teeth Whitening", "In-office whitening, one session.", 60, Decimal("8000.00"), 5),
    ],
    faqs=[
        DemoFaq("Do you accept insurance?", "We accept most major insurance providers. Please call ahead to confirm coverage.", "billing", 1),
        DemoFaq("How much does a routine cleaning cost?", "A routine cleaning is 1500 BDT. We offer 10% off your first visit.", "pricing", 2),
        DemoFaq("Do I need an appointment for emergencies?", "We reserve same-day slots for emergencies. Please call directly.", "scheduling", 3),
        DemoFaq("What are your operating hours?", "We are open Monday to Saturday, 9 AM to 6 PM. Closed Sundays.", "hours", 4),
        DemoFaq("Do you treat children?", "Yes, we welcome patients of all ages, including children.", "services", 5),
        DemoFaq("How long does a root canal take?", "Most root canals are completed in a single 90-minute appointment.", "services", 6),
        DemoFaq("Is teeth whitening safe?", "Our in-office whitening is safe and supervised by a licensed dentist.", "services", 7),
        DemoFaq("How do I cancel an appointment?", "Please give at least 24 hours notice to avoid a cancellation fee.", "policy", 8),
        DemoFaq("Do you offer payment plans?", "Yes, payment plans are available for treatments above 10,000 BDT.", "billing", 9),
        DemoFaq("Where are you located?", "We are in Gulshan-2, near the lake. Detailed directions on our website.", "location", 10),
    ],
)


QUICK_HVAC = DemoBusiness(
    slug="quick-hvac",
    name="Quick HVAC Services",
    industry="hvac",
    timezone_name="Asia/Dhaka",
    admin_email="owner@quickhvac.com",
    admin_full_name="Karim Ahmed",
    services=[
        DemoService("AC Tune-Up", "Routine inspection, filter clean, refrigerant check.", 60, Decimal("2500.00"), 1),
        DemoService("AC Repair Diagnostic", "On-site diagnostic visit, fee waived if repair booked.", 45, Decimal("1500.00"), 2),
        DemoService("Full AC Installation", "Split AC installation including labor and parts.", 180, Decimal("8000.00"), 3, buffer_minutes=30),
        DemoService("Duct Cleaning", "Whole-house duct cleaning, deodorize included.", 120, Decimal("6500.00"), 4),
        DemoService("Emergency Service Call", "Same-day visit for non-functional AC units.", 90, Decimal("4000.00"), 5),
    ],
    faqs=[
        DemoFaq("Do you offer same-day service?", "Yes, for emergency calls we usually arrive within 4 hours.", "scheduling", 1),
        DemoFaq("How much does an AC tune-up cost?", "A tune-up is 2500 BDT and takes about 60 minutes.", "pricing", 2),
        DemoFaq("Do you service all AC brands?", "Yes, we service all major brands including LG, Samsung, Daikin, and Gree.", "services", 3),
        DemoFaq("What is your warranty?", "All repairs come with a 90-day warranty on labor and parts.", "policy", 4),
        DemoFaq("Are you licensed and insured?", "Yes, fully licensed and insured for residential and light commercial work.", "policy", 5),
        DemoFaq("Do you provide free estimates?", "Yes, estimates for installations are always free.", "pricing", 6),
        DemoFaq("What are your hours?", "Monday to Saturday, 9 AM to 6 PM. Emergency calls Sundays by arrangement.", "hours", 7),
        DemoFaq("Do you work on commercial buildings?", "We handle light commercial work. Heavy industrial referred to partners.", "services", 8),
        DemoFaq("How often should I service my AC?", "Once a year minimum, ideally before the hot season begins.", "services", 9),
        DemoFaq("Where do you operate?", "Dhaka and surrounding suburbs within 25 km of our shop.", "location", 10),
    ],
)


RAHMAN_LAW = DemoBusiness(
    slug="rahman-law",
    name="Rahman & Associates Law",
    industry="legal",
    timezone_name="Asia/Dhaka",
    admin_email="owner@rahmanlaw.com",
    admin_full_name="Adv. Fatima Rahman",
    services=[
        DemoService("Initial Consultation", "30-minute discovery consultation, fixed fee.", 30, Decimal("3000.00"), 1),
        DemoService("Contract Review", "Review and notes on a single contract up to 20 pages.", 60, Decimal("8000.00"), 2),
        DemoService("Property Title Verification", "Search and verification of property title chain.", 120, Decimal("15000.00"), 3),
        DemoService("Will Drafting", "Drafting a single-page will, includes one revision.", 90, Decimal("10000.00"), 4),
        DemoService("Court Representation Strategy Session", "Pre-trial strategy meeting, 2 hours.", 120, Decimal("12000.00"), 5),
    ],
    faqs=[
        DemoFaq("Do you offer free consultations?", "Initial consultations are 3000 BDT for 30 minutes. Fee is credited toward future work.", "pricing", 1),
        DemoFaq("What areas of law do you practice?", "Civil, contract, property, and family law. Criminal cases referred to partners.", "services", 2),
        DemoFaq("How are fees structured?", "Most matters are flat-fee. Complex litigation may be billed hourly with prior agreement.", "billing", 3),
        DemoFaq("Do you handle property disputes?", "Yes, including title verification, partition, and possession matters.", "services", 4),
        DemoFaq("Are consultations confidential?", "Yes, all consultations are privileged and confidential.", "policy", 5),
        DemoFaq("Where is your office located?", "Dhanmondi, Road 27, opposite Square Hospital.", "location", 6),
        DemoFaq("What are your office hours?", "Monday to Saturday, 9 AM to 6 PM by appointment.", "hours", 7),
        DemoFaq("Do you accept new clients?", "Yes, subject to a brief conflict check before the first meeting.", "policy", 8),
        DemoFaq("Can you draft a will online?", "We require a brief in-person meeting to verify identity and discuss wishes.", "services", 9),
        DemoFaq("How quickly can you respond to urgent matters?", "Urgent matters typically receive a callback within 24 hours.", "scheduling", 10),
    ],
)


ALL_DEMOS: list[DemoBusiness] = [DHAKA_DENTAL, QUICK_HVAC, RAHMAN_LAW]


# Standard demo hours: Mon-Sat 9 AM - 6 PM, Sunday closed
_OPEN_DAYS: list[DayOfWeek] = [
    DayOfWeek.MON,
    DayOfWeek.TUE,
    DayOfWeek.WED,
    DayOfWeek.THU,
    DayOfWeek.FRI,
    DayOfWeek.SAT,
]
_CLOSED_DAYS: list[DayOfWeek] = [DayOfWeek.SUN]


# ---------------------------------------------------------------------------
# Seeding
# ---------------------------------------------------------------------------

@dataclass
class SeedSummary:
    businesses_created: int = 0
    businesses_skipped: int = 0
    services_created: int = 0
    hours_created: int = 0
    faqs_created: int = 0
    admins_created: int = 0


async def _seed_one_business(
    session: AsyncSession,
    demo: DemoBusiness,
    summary: SeedSummary,
) -> None:
    existing = await session.execute(
        select(Business).where(Business.slug == demo.slug)
    )
    if existing.scalar_one_or_none() is not None:
        print(f"  - {demo.slug}: already exists; skipping.")
        summary.businesses_skipped += 1
        return

    business = Business(
        slug=demo.slug,
        name=demo.name,
        industry=demo.industry,
        timezone=demo.timezone_name,
        status=BusinessStatus.ACTIVE,
    )
    session.add(business)
    await session.flush()  # populate business.id
    summary.businesses_created += 1

    session.add(BusinessSetting(business_id=business.id))

    admin = User(
        email=demo.admin_email,
        password_hash=hash_password(_DEMO_PASSWORD),
        full_name=demo.admin_full_name,
        role=UserRole.BUSINESS_ADMIN,
        business_id=business.id,
    )
    session.add(admin)
    summary.admins_created += 1

    for svc in demo.services:
        session.add(Service(
            business_id=business.id,
            name=svc.name,
            description=svc.description,
            duration_minutes=svc.duration_minutes,
            buffer_minutes=svc.buffer_minutes,
            price=svc.price,
            display_order=svc.display_order,
            is_active=True,
        ))
        summary.services_created += 1

    for day in _OPEN_DAYS:
        session.add(OperatingHours(
            business_id=business.id,
            day_of_week=day,
            open_time=time(9, 0),
            close_time=time(18, 0),
            is_closed=False,
        ))
        summary.hours_created += 1
    for day in _CLOSED_DAYS:
        session.add(OperatingHours(
            business_id=business.id,
            day_of_week=day,
            open_time=time(0, 0),
            close_time=time(0, 0),
            is_closed=True,
        ))
        summary.hours_created += 1

    for f in demo.faqs:
        session.add(Faq(
            business_id=business.id,
            question=f.question,
            answer=f.answer,
            category=f.category,
            display_order=f.display_order,
            is_active=True,
        ))
        summary.faqs_created += 1

    print(f"  + {demo.slug}: created ({len(demo.services)} services, "
          f"{len(_OPEN_DAYS) + len(_CLOSED_DAYS)} hours, {len(demo.faqs)} FAQs)")


async def _run() -> int:
    summary = SeedSummary()

    async with async_session_factory() as session:
        print("Seeding demo businesses...")
        for demo in ALL_DEMOS:
            await _seed_one_business(session, demo, summary)
        await session.commit()

    print()
    print("Summary:")
    print(f"  Businesses created: {summary.businesses_created}")
    print(f"  Businesses skipped (already existed): {summary.businesses_skipped}")
    print(f"  Admins created:     {summary.admins_created}")
    print(f"  Services created:   {summary.services_created}")
    print(f"  Hours rows created: {summary.hours_created}")
    print(f"  FAQs created:       {summary.faqs_created}")
    print()
    if summary.businesses_created > 0:
        print(f"Demo admin passwords are all '{_DEMO_PASSWORD}'. For local demo use only.")

    return 0


async def _main_async() -> int:
    try:
        return await _run()
    finally:
        await engine.dispose()


def main() -> None:
    sys.exit(asyncio.run(_main_async()))


if __name__ == "__main__":
    main()
