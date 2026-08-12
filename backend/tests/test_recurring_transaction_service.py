import uuid
from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.transaction import Transaction
from app.schemas.recurring_transaction import RecurringTransactionCreate, RecurringTransactionUpdate
from app.services.recurring_transaction_service import (
    _advance_date,
    adjust_weekend_date,
    create_recurring_transaction,
    delete_recurring_transaction,
    generate_pending,
    get_occurrences_in_range,
    get_recurring_transaction,
    get_recurring_transactions,
    update_recurring_transaction,
)


@pytest_asyncio.fixture
async def test_account_for_recurring(session: AsyncSession, test_user) -> Account:
    account = Account(
        id=uuid.uuid4(),
        user_id=test_user.id,
        name="RecurAcc",
        type="checking",
        balance=Decimal("10000"),
        currency="BRL",
    )
    session.add(account)
    await session.commit()
    await session.refresh(account)
    return account


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_recurring_transaction(
    session: AsyncSession, test_user, test_workspace, test_account_for_recurring
):
    data = RecurringTransactionCreate(
        description="Netflix",
        amount=Decimal("39.90"),
        type="debit",
        frequency="monthly",
        start_date=date(2025, 1, 15),
        account_id=test_account_for_recurring.id,
    )
    rec = await create_recurring_transaction(session, test_workspace.id, test_user.id, data)

    assert rec.id is not None
    assert rec.description == "Netflix"
    assert rec.amount == Decimal("39.90")
    assert rec.frequency == "monthly"
    assert rec.next_occurrence == date(2025, 1, 15)
    assert rec.is_active is True


@pytest.mark.asyncio
async def test_create_with_skip_first(session: AsyncSession, test_user, test_workspace, test_account_for_recurring):
    data = RecurringTransactionCreate(
        description="Rent",
        amount=Decimal("2000"),
        type="debit",
        frequency="monthly",
        start_date=date(2025, 3, 1),
        account_id=test_account_for_recurring.id,
        skip_first=True,
    )
    rec = await create_recurring_transaction(session, test_workspace.id, test_user.id, data)

    # skip_first should advance to next month
    assert rec.start_date == date(2025, 3, 1)
    assert rec.next_occurrence == date(2025, 4, 1)


@pytest.mark.asyncio
async def test_get_recurring_transactions(
    session: AsyncSession, test_user, test_workspace, test_account_for_recurring
):
    for desc, dt in [("Sub1", date(2025, 1, 1)), ("Sub2", date(2025, 2, 1))]:
        await create_recurring_transaction(
            session,
            test_workspace.id, test_user.id,
            RecurringTransactionCreate(
                description=desc,
                amount=Decimal("10"),
                type="debit",
                frequency="monthly",
                start_date=dt,
                account_id=test_account_for_recurring.id,
            ),
        )

    result = await get_recurring_transactions(session, test_workspace.id)
    assert len(result) >= 2

    # Ordered by next_occurrence
    dates = [r.next_occurrence for r in result]
    assert dates == sorted(dates)


@pytest.mark.asyncio
async def test_get_recurring_transaction_by_id(
    session: AsyncSession, test_user, test_workspace, test_account_for_recurring
):
    created = await create_recurring_transaction(
        session,
        test_workspace.id, test_user.id,
        RecurringTransactionCreate(
            description="Lookup",
            amount=Decimal("50"),
            type="debit",
            frequency="weekly",
            start_date=date(2025, 6, 1),
            account_id=test_account_for_recurring.id,
        ),
    )
    fetched = await get_recurring_transaction(session, created.id, test_workspace.id)
    assert fetched is not None
    assert fetched.id == created.id


@pytest.mark.asyncio
async def test_get_recurring_transaction_not_found(session: AsyncSession, test_user, test_workspace):
    result = await get_recurring_transaction(session, uuid.uuid4(), test_workspace.id)
    assert result is None


@pytest.mark.asyncio
async def test_update_recurring_transaction(
    session: AsyncSession, test_user, test_workspace, test_account_for_recurring
):
    rec = await create_recurring_transaction(
        session,
        test_workspace.id, test_user.id,
        RecurringTransactionCreate(
            description="Old",
            amount=Decimal("100"),
            type="debit",
            frequency="monthly",
            start_date=date(2025, 1, 1),
            account_id=test_account_for_recurring.id,
        ),
    )
    updated = await update_recurring_transaction(
        session,
        rec.id,
        test_workspace.id,
        RecurringTransactionUpdate(description="Updated", amount=Decimal("150")),
    )
    assert updated is not None
    assert updated.description == "Updated"
    assert updated.amount == Decimal("150")


@pytest.mark.asyncio
async def test_update_recurring_not_found(session: AsyncSession, test_user, test_workspace):
    result = await update_recurring_transaction(
        session,
        uuid.uuid4(),
        test_workspace.id,
        RecurringTransactionUpdate(description="Nope"),
    )
    assert result is None


@pytest.mark.asyncio
async def test_delete_recurring_transaction(
    session: AsyncSession, test_user, test_workspace, test_account_for_recurring
):
    rec = await create_recurring_transaction(
        session,
        test_workspace.id, test_user.id,
        RecurringTransactionCreate(
            description="ToDelete",
            amount=Decimal("10"),
            type="debit",
            frequency="monthly",
            start_date=date(2025, 1, 1),
            account_id=test_account_for_recurring.id,
        ),
    )
    assert await delete_recurring_transaction(session, rec.id, test_workspace.id) is True
    assert await get_recurring_transaction(session, rec.id, test_workspace.id) is None


@pytest.mark.asyncio
async def test_delete_recurring_not_found(session: AsyncSession, test_user, test_workspace):
    assert await delete_recurring_transaction(session, uuid.uuid4(), test_workspace.id) is False


# ---------------------------------------------------------------------------
# _advance_date
# ---------------------------------------------------------------------------


def test_advance_date_monthly():
    assert _advance_date(date(2025, 1, 15), "monthly") == date(2025, 2, 15)
    assert _advance_date(date(2025, 12, 10), "monthly") == date(2026, 1, 10)


def test_advance_date_monthly_overflow():
    # Jan 31 -> Feb should clamp to 28
    assert _advance_date(date(2025, 1, 31), "monthly") == date(2025, 2, 28)
    # Leap year: Jan 31 -> Feb 29
    assert _advance_date(date(2024, 1, 31), "monthly") == date(2024, 2, 29)


def test_advance_date_weekly():
    assert _advance_date(date(2025, 1, 1), "weekly") == date(2025, 1, 8)
    assert _advance_date(date(2025, 12, 29), "weekly") == date(2026, 1, 5)


def test_advance_date_yearly():
    assert _advance_date(date(2025, 3, 15), "yearly") == date(2026, 3, 15)
    # Leap year: Feb 29 -> Feb 28 next year
    assert _advance_date(date(2024, 2, 29), "yearly") == date(2025, 2, 28)


def test_advance_date_monthly_intended_day_recovers_after_february():
    # After Jan 31 clamps to Feb 28, advancing again must hit Mar 31 — not drift to Mar 28.
    feb = _advance_date(date(2026, 1, 31), "monthly", intended_day=31)
    assert feb == date(2026, 2, 28)
    mar = _advance_date(feb, "monthly", intended_day=31)
    assert mar == date(2026, 3, 31)
    apr = _advance_date(mar, "monthly", intended_day=31)
    assert apr == date(2026, 4, 30)  # April has 30 days
    may = _advance_date(apr, "monthly", intended_day=31)
    assert may == date(2026, 5, 31)


def test_advance_date_monthly_intended_day_30():
    # Day 30 pattern: Jan 30 -> Feb 28 -> Mar 30 (not Mar 28).
    feb = _advance_date(date(2026, 1, 30), "monthly", intended_day=30)
    assert feb == date(2026, 2, 28)
    mar = _advance_date(feb, "monthly", intended_day=30)
    assert mar == date(2026, 3, 30)


def test_advance_date_yearly_intended_day_leap_recovery():
    # Feb 29 on a leap year should recover to Feb 29 four years later, not stick at 28.
    y1 = _advance_date(date(2024, 2, 29), "yearly", intended_day=29)
    assert y1 == date(2025, 2, 28)
    y2 = _advance_date(y1, "yearly", intended_day=29)
    assert y2 == date(2026, 2, 28)
    y3 = _advance_date(y2, "yearly", intended_day=29)
    assert y3 == date(2027, 2, 28)
    y4 = _advance_date(y3, "yearly", intended_day=29)
    assert y4 == date(2028, 2, 29)


def test_advance_date_quarterly():
    assert _advance_date(date(2026, 1, 15), "quarterly") == date(2026, 4, 15)
    assert _advance_date(date(2026, 11, 15), "quarterly") == date(2027, 2, 15)


def test_advance_date_quarterly_intended_day_recovers_after_clamping():
    april = _advance_date(date(2026, 1, 31), "quarterly", intended_day=31)
    assert april == date(2026, 4, 30)
    july = _advance_date(april, "quarterly", intended_day=31)
    assert july == date(2026, 7, 31)
    october = _advance_date(july, "quarterly", intended_day=31)
    assert october == date(2026, 10, 31)
    january = _advance_date(october, "quarterly", intended_day=31)
    assert january == date(2027, 1, 31)


def test_advance_date_quarterly_leap_year_clamping_recovers():
    february = _advance_date(date(2023, 11, 30), "quarterly", intended_day=30)
    assert february == date(2024, 2, 29)
    may = _advance_date(february, "quarterly", intended_day=30)
    assert may == date(2024, 5, 30)


@pytest.mark.parametrize(
    ("nominal", "policy", "expected"),
    [
        (date(2026, 8, 1), "none", date(2026, 8, 1)),
        (date(2026, 8, 1), "previous_friday", date(2026, 7, 31)),
        (date(2026, 8, 1), "next_monday", date(2026, 8, 3)),
        (date(2026, 8, 2), "none", date(2026, 8, 2)),
        (date(2026, 8, 2), "previous_friday", date(2026, 7, 31)),
        (date(2026, 8, 2), "next_monday", date(2026, 8, 3)),
        (date(2026, 8, 3), "none", date(2026, 8, 3)),
        (date(2026, 8, 3), "previous_friday", date(2026, 8, 3)),
        (date(2026, 8, 3), "next_monday", date(2026, 8, 3)),
        (date(2026, 8, 7), "none", date(2026, 8, 7)),
        (date(2026, 8, 7), "previous_friday", date(2026, 8, 7)),
        (date(2026, 8, 7), "next_monday", date(2026, 8, 7)),
    ],
)
def test_adjust_weekend_date(nominal, policy, expected):
    assert adjust_weekend_date(nominal, policy) == expected


def test_adjust_weekend_date_rejects_unsupported_policy_on_weekday():
    with pytest.raises(
        ValueError, match="Unsupported weekend adjustment: nearest_weekday"
    ):
        adjust_weekend_date(date(2026, 8, 3), "nearest_weekday")


@pytest.mark.parametrize(
    ("frequency", "start", "intended_day", "expected"),
    [
        (
            "weekly",
            date(2026, 8, 1),
            1,
            [
                (date(2026, 8, 1), date(2026, 7, 31)),
                (date(2026, 8, 8), date(2026, 8, 7)),
                (date(2026, 8, 15), date(2026, 8, 14)),
            ],
        ),
        (
            "monthly",
            date(2026, 1, 31),
            31,
            [
                (date(2026, 1, 31), date(2026, 1, 30)),
                (date(2026, 2, 28), date(2026, 2, 27)),
                (date(2026, 3, 31), date(2026, 3, 31)),
            ],
        ),
        (
            "quarterly",
            date(2026, 1, 31),
            31,
            [
                (date(2026, 1, 31), date(2026, 1, 30)),
                (date(2026, 4, 30), date(2026, 4, 30)),
                (date(2026, 7, 31), date(2026, 7, 31)),
            ],
        ),
        (
            "yearly",
            date(2024, 2, 29),
            29,
            [
                (date(2024, 2, 29), date(2024, 2, 29)),
                (date(2025, 2, 28), date(2025, 2, 28)),
                (date(2026, 2, 28), date(2026, 2, 27)),
            ],
        ),
    ],
)
def test_weekend_adjustment_never_changes_nominal_cadence(
    frequency, start, intended_day, expected
):
    current = start
    actual = []
    for _ in expected:
        actual.append((current, adjust_weekend_date(current, "previous_friday")))
        current = _advance_date(current, frequency, intended_day=intended_day)
    assert actual == expected


def test_occurrence_range_uses_effective_date_across_month_boundary():
    july = get_occurrences_in_range(
        start=date(2026, 8, 1),
        frequency="monthly",
        end_date=None,
        range_start=date(2026, 7, 1),
        range_end=date(2026, 8, 1),
        weekend_adjustment="previous_friday",
    )
    august = get_occurrences_in_range(
        start=date(2026, 8, 1),
        frequency="monthly",
        end_date=None,
        range_start=date(2026, 8, 1),
        range_end=date(2026, 9, 1),
        weekend_adjustment="previous_friday",
    )

    assert july == [date(2026, 7, 31)]
    assert august == []
    assert july.count(date(2026, 7, 31)) + august.count(date(2026, 7, 31)) == 1


def test_occurrence_range_moves_sunday_to_following_monday():
    assert get_occurrences_in_range(
        start=date(2026, 8, 2),
        frequency="monthly",
        end_date=None,
        range_start=date(2026, 8, 1),
        range_end=date(2026, 9, 1),
        weekend_adjustment="next_monday",
    ) == [date(2026, 8, 3)]


# ---------------------------------------------------------------------------
# get_occurrences_in_range
# ---------------------------------------------------------------------------


def test_get_occurrences_in_range_monthly():
    occurrences = get_occurrences_in_range(
        start=date(2025, 1, 1),
        frequency="monthly",
        end_date=None,
        range_start=date(2025, 3, 1),
        range_end=date(2025, 6, 1),
    )
    assert occurrences == [date(2025, 3, 1), date(2025, 4, 1), date(2025, 5, 1)]


def test_get_occurrences_in_range_respects_end_date():
    occurrences = get_occurrences_in_range(
        start=date(2025, 1, 1),
        frequency="monthly",
        end_date=date(2025, 4, 15),
        range_start=date(2025, 3, 1),
        range_end=date(2025, 12, 1),
    )
    assert occurrences == [date(2025, 3, 1), date(2025, 4, 1)]


def test_get_occurrences_in_range_weekly():
    occurrences = get_occurrences_in_range(
        start=date(2025, 1, 6),
        frequency="weekly",
        end_date=None,
        range_start=date(2025, 1, 6),
        range_end=date(2025, 1, 27),
    )
    assert len(occurrences) == 3  # Jan 6, 13, 20 (range_end is exclusive)


def test_get_occurrences_in_range_empty():
    occurrences = get_occurrences_in_range(
        start=date(2025, 6, 1),
        frequency="monthly",
        end_date=None,
        range_start=date(2025, 1, 1),
        range_end=date(2025, 3, 1),
    )
    assert occurrences == []


def test_get_occurrences_in_range_monthly_day_31_does_not_drift():
    # Regression test for #67: after Feb clamps to 28, subsequent months must
    # recover to their true month-end (31 / 30 / 31 / 30) instead of sticking at 28.
    occurrences = get_occurrences_in_range(
        start=date(2026, 1, 31),
        frequency="monthly",
        end_date=None,
        range_start=date(2026, 1, 1),
        range_end=date(2026, 7, 1),
        intended_day=31,
    )
    assert occurrences == [
        date(2026, 1, 31),
        date(2026, 2, 28),
        date(2026, 3, 31),
        date(2026, 4, 30),
        date(2026, 5, 31),
        date(2026, 6, 30),
    ]


def test_get_occurrences_in_range_monthly_day_30_does_not_drift():
    occurrences = get_occurrences_in_range(
        start=date(2026, 1, 30),
        frequency="monthly",
        end_date=None,
        range_start=date(2026, 1, 1),
        range_end=date(2026, 7, 1),
        intended_day=30,
    )
    assert occurrences == [
        date(2026, 1, 30),
        date(2026, 2, 28),
        date(2026, 3, 30),
        date(2026, 4, 30),
        date(2026, 5, 30),
        date(2026, 6, 30),
    ]


def test_get_occurrences_in_range_monthly_day_29_does_not_drift():
    occurrences = get_occurrences_in_range(
        start=date(2026, 1, 29),
        frequency="monthly",
        end_date=None,
        range_start=date(2026, 1, 1),
        range_end=date(2026, 7, 1),
        intended_day=29,
    )
    assert occurrences == [
        date(2026, 1, 29),
        date(2026, 2, 28),
        date(2026, 3, 29),
        date(2026, 4, 29),
        date(2026, 5, 29),
        date(2026, 6, 29),
    ]


def test_get_occurrences_in_range_quarterly():
    occurrences = get_occurrences_in_range(
        start=date(2026, 1, 31),
        frequency="quarterly",
        end_date=None,
        range_start=date(2026, 1, 1),
        range_end=date(2027, 2, 1),
        intended_day=31,
    )
    assert occurrences == [
        date(2026, 1, 31),
        date(2026, 4, 30),
        date(2026, 7, 31),
        date(2026, 10, 31),
        date(2027, 1, 31),
    ]


def test_get_occurrences_in_range_quarterly_respects_end_date():
    occurrences = get_occurrences_in_range(
        start=date(2026, 1, 15),
        frequency="quarterly",
        end_date=date(2026, 7, 1),
        range_start=date(2026, 1, 1),
        range_end=date(2027, 1, 1),
    )
    assert occurrences == [date(2026, 1, 15), date(2026, 4, 15)]


# ---------------------------------------------------------------------------
# generate_pending
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_pending(session: AsyncSession, test_user, test_workspace, test_account_for_recurring):
    rec = await create_recurring_transaction(
        session,
        test_workspace.id, test_user.id,
        RecurringTransactionCreate(
            description="Monthly Sub",
            amount=Decimal("29.90"),
            type="debit",
            frequency="monthly",
            start_date=date(2025, 1, 1),
            account_id=test_account_for_recurring.id,
        ),
    )

    with _without_ahead():
        count = await generate_pending(session, test_user.id, up_to=date(2025, 3, 15))
    assert count == 3  # Jan, Feb, Mar

    # Verify transactions were created
    result = await session.execute(
        select(Transaction).where(
            Transaction.user_id == test_user.id,
            Transaction.source == "recurring",
            Transaction.description == "Monthly Sub",
        )
    )
    txns = result.scalars().all()
    assert len(txns) == 3

    # next_occurrence should be advanced past cutoff
    await session.refresh(rec)
    assert rec.next_occurrence == date(2025, 4, 1)


@pytest.mark.asyncio
async def test_generate_pending_quarterly_respects_end_date(
    session: AsyncSession, test_user, test_workspace, test_account_for_recurring
):
    rec = await create_recurring_transaction(
        session,
        test_workspace.id,
        test_user.id,
        RecurringTransactionCreate(
            description="Quarterly Insurance",
            amount=Decimal("300"),
            type="debit",
            frequency="quarterly",
            day_of_month=30,
            start_date=date(2023, 11, 30),
            end_date=date(2024, 5, 30),
            account_id=test_account_for_recurring.id,
        ),
    )

    with _without_ahead():
        count = await generate_pending(session, test_user.id, up_to=date(2024, 12, 31))
    assert count == 3

    result = await session.execute(
        select(Transaction)
        .where(
            Transaction.recurring_transaction_id == rec.id,
            Transaction.source == "recurring",
        )
        .order_by(Transaction.date)
    )
    assert [transaction.date for transaction in result.scalars()] == [
        date(2023, 11, 30),
        date(2024, 2, 29),
        date(2024, 5, 30),
    ]

    await session.refresh(rec)
    assert rec.next_occurrence == date(2024, 8, 30)
    assert rec.is_active is False


@pytest.mark.asyncio
async def test_generate_pending_deactivates_past_end_date(
    session: AsyncSession, test_user, test_workspace, test_account_for_recurring
):
    rec = await create_recurring_transaction(
        session,
        test_workspace.id, test_user.id,
        RecurringTransactionCreate(
            description="Short Sub",
            amount=Decimal("10"),
            type="debit",
            frequency="monthly",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 2, 15),
            account_id=test_account_for_recurring.id,
        ),
    )

    with _without_ahead():
        count = await generate_pending(session, test_user.id, up_to=date(2025, 12, 31))
    # Should create Jan and Feb (Feb 1 <= Feb 15), then deactivate
    assert count == 2

    await session.refresh(rec)
    assert rec.is_active is False


@pytest.mark.asyncio
async def test_generate_pending_no_duplicates(
    session: AsyncSession, test_user, test_workspace, test_account_for_recurring
):
    await create_recurring_transaction(
        session,
        test_workspace.id, test_user.id,
        RecurringTransactionCreate(
            description="NoDup",
            amount=Decimal("5"),
            type="debit",
            frequency="monthly",
            start_date=date(2025, 1, 1),
            account_id=test_account_for_recurring.id,
        ),
    )

    with _without_ahead():
        # Generate once
        count1 = await generate_pending(session, test_user.id, up_to=date(2025, 3, 1))
        # Generate again with same cutoff — should produce 0
        count2 = await generate_pending(session, test_user.id, up_to=date(2025, 3, 1))
    assert count1 == 3
    assert count2 == 0


# ---------------------------------------------------------------------------
# generate_pending with RECURRING_GENERATE_AHEAD (flag ON)
# ---------------------------------------------------------------------------


def _ahead_settings(ahead: bool = True):
    from types import SimpleNamespace

    return SimpleNamespace(recurring_generate_ahead=ahead)


def _with_ahead():
    from unittest.mock import patch

    return patch(
        "app.services.recurring_transaction_service.get_settings",
        return_value=_ahead_settings(True),
    )


def _without_ahead():
    from unittest.mock import patch

    return patch(
        "app.services.recurring_transaction_service.get_settings",
        return_value=_ahead_settings(False),
    )


async def _generated_rows(session: AsyncSession, description: str) -> list[Transaction]:
    result = await session.execute(
        select(Transaction)
        .where(
            Transaction.source == "recurring",
            Transaction.description == description,
        )
        .order_by(Transaction.date)
    )
    return list(result.scalars().all())


@pytest.mark.asyncio
async def test_generate_pending_ahead_creates_pending_row_beyond_cutoff(
    session: AsyncSession, test_user, test_workspace, test_account_for_recurring
):
    """Flag ON: one occurrence is created beyond the cutoff, always pending,
    and next_occurrence stays at the next actual due date (not advanced past the ahead row)."""
    rec = await create_recurring_transaction(
        session,
        test_workspace.id, test_user.id,
        RecurringTransactionCreate(
            description="Ahead Sub",
            amount=Decimal("29.90"),
            type="debit",
            frequency="monthly",
            start_date=date(2025, 1, 1),
            account_id=test_account_for_recurring.id,
        ),
    )

    with _with_ahead():
        count = await generate_pending(session, test_user.id, up_to=date(2025, 1, 1))

    # Jan 1 (due, loop) + Feb 1 (ahead step) = 2 pending rows.
    assert count == 2
    rows = await _generated_rows(session, "Ahead Sub")
    assert [r.date for r in rows] == [date(2025, 1, 1), date(2025, 2, 1)]
    assert all(r.status == "pending" for r in rows)

    await session.refresh(rec)
    # next_occurrence stays at the next actual due date (Feb 1)
    assert rec.next_occurrence == date(2025, 2, 1)


@pytest.mark.asyncio
async def test_generate_pending_ahead_backlog_all_pending(
    session: AsyncSession, test_user, test_workspace, test_account_for_recurring
):
    """Flag ON, backlog catch-up: loop rows (due occurrences) are pending too,
    not just the ahead row."""
    await create_recurring_transaction(
        session,
        test_workspace.id, test_user.id,
        RecurringTransactionCreate(
            description="Backlog Sub",
            amount=Decimal("10"),
            type="debit",
            frequency="monthly",
            start_date=date(2025, 1, 1),
            account_id=test_account_for_recurring.id,
        ),
    )

    with _with_ahead():
        count = await generate_pending(session, test_user.id, up_to=date(2025, 3, 1))

    # Jan, Feb, Mar (loop) + Apr (ahead) = 4 pending rows.
    assert count == 4
    rows = await _generated_rows(session, "Backlog Sub")
    assert [r.date for r in rows] == [
        date(2025, 1, 1),
        date(2025, 2, 1),
        date(2025, 3, 1),
        date(2025, 4, 1),
    ]
    assert all(r.status == "pending" for r in rows)


@pytest.mark.asyncio
async def test_generate_pending_ahead_idempotent(
    session: AsyncSession, test_user, test_workspace, test_account_for_recurring
):
    """Flag ON: re-running with the same cutoff creates no duplicates."""
    await create_recurring_transaction(
        session,
        test_workspace.id, test_user.id,
        RecurringTransactionCreate(
            description="Idem Sub",
            amount=Decimal("5"),
            type="debit",
            frequency="monthly",
            start_date=date(2025, 1, 1),
            account_id=test_account_for_recurring.id,
        ),
    )

    with _with_ahead():
        count1 = await generate_pending(session, test_user.id, up_to=date(2025, 1, 1))
        count2 = await generate_pending(session, test_user.id, up_to=date(2025, 1, 1))

    assert count1 == 2
    assert count2 == 0
    assert len(await _generated_rows(session, "Idem Sub")) == 2


@pytest.mark.asyncio
async def test_generate_pending_ahead_no_auto_flip(
    session: AsyncSession, test_user, test_workspace, test_account_for_recurring
):
    """Flag ON: later generate_pending runs leave generated rows pending —
    they are never auto-flipped to posted."""
    await create_recurring_transaction(
        session,
        test_workspace.id, test_user.id,
        RecurringTransactionCreate(
            description="NoFlip Sub",
            amount=Decimal("7"),
            type="debit",
            frequency="monthly",
            start_date=date(2025, 1, 1),
            account_id=test_account_for_recurring.id,
        ),
    )

    with _with_ahead():
        count1 = await generate_pending(session, test_user.id, up_to=date(2025, 1, 1))
        # A later run (next period) still materializes more, but never flips.
        count2 = await generate_pending(session, test_user.id, up_to=date(2025, 3, 1))

    assert count1 == 2  # Jan (loop) + Feb (ahead)
    assert count2 == 2  # Mar (loop) + Apr (ahead)
    rows = await _generated_rows(session, "NoFlip Sub")
    assert len(rows) == 4
    assert all(r.status == "pending" for r in rows)


@pytest.mark.asyncio
async def test_generate_pending_ahead_end_date_deactivates(
    session: AsyncSession, test_user, test_workspace, test_account_for_recurring
):
    """Flag ON: ahead date beyond end_date → no ahead row, rule deactivates."""
    rec = await create_recurring_transaction(
        session,
        test_workspace.id, test_user.id,
        RecurringTransactionCreate(
            description="Short Ahead",
            amount=Decimal("12"),
            type="debit",
            frequency="monthly",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 15),
            account_id=test_account_for_recurring.id,
        ),
    )

    with _with_ahead():
        count = await generate_pending(session, test_user.id, up_to=date(2025, 1, 1))

    # Only the due Jan row exists; the ahead date (Feb 1) is past end_date.
    assert count == 1
    rows = await _generated_rows(session, "Short Ahead")
    assert [r.date for r in rows] == [date(2025, 1, 1)]
    assert rows[0].status == "pending"

    await session.refresh(rec)
    assert rec.is_active is False
    # next_occurrence stays at Feb 1 (next due date, past end_date)
    assert rec.next_occurrence == date(2025, 2, 1)


@pytest.mark.asyncio
async def test_generate_pending_ahead_real_tx_linked_not_duplicated(
    session: AsyncSession, test_user, test_workspace, test_account_for_recurring
):
    """Flag ON: a real transaction already covering the ahead date is linked,
    no duplicate placeholder is written for it."""
    rec = await create_recurring_transaction(
        session,
        test_workspace.id, test_user.id,
        RecurringTransactionCreate(
            description="Netflix Subscription",
            amount=Decimal("39.90"),
            type="debit",
            currency="BRL",
            frequency="monthly",
            start_date=date(2025, 1, 1),
            account_id=test_account_for_recurring.id,
        ),
    )
    # Real (manual) charge already covers the ahead date (Feb 1).
    real = Transaction(
        user_id=test_user.id,
        account_id=test_account_for_recurring.id,
        description="NETFLIX SUBSCRIPTION",
        amount=Decimal("39.90"),
        currency="BRL",
        date=date(2025, 2, 1),
        type="debit",
        source="manual",
        status="posted",
    )
    session.add(real)
    await session.commit()

    with _with_ahead():
        count = await generate_pending(session, test_user.id, up_to=date(2025, 1, 1))

    # Jan placeholder only; Feb is covered by the linked real charge.
    assert count == 1
    rows = await _generated_rows(session, "Netflix Subscription")
    assert [r.date for r in rows] == [date(2025, 1, 1)]

    await session.refresh(real)
    assert real.recurring_transaction_id == rec.id

    await session.refresh(rec)
    # next_occurrence stays at Feb 1 (next due date, real tx covers ahead date)
    assert rec.next_occurrence == date(2025, 2, 1)


@pytest.mark.asyncio
async def test_generate_pending_ahead_steady_state_materializes_one_period_ahead(
    session: AsyncSession, test_user, test_workspace, test_account_for_recurring
):
    """Flag ON, plan timeline: a rule created Dec 1 materializes Jan 1 (ahead)
    on the Dec 1 run. On the Jan 1 run the loop is empty (Jan is already
    pending), but the ahead step still materializes Feb 1 — one period ahead —
    because next_occurrence is exactly the first pattern occurrence after the
    cutoff. This is the steady state that a SELECT restricted to due rules
    would silently miss."""
    rec = await create_recurring_transaction(
        session,
        test_workspace.id, test_user.id,
        RecurringTransactionCreate(
            description="Steady Sub",
            amount=Decimal("15"),
            type="debit",
            frequency="monthly",
            start_date=date(2025, 12, 1),
            account_id=test_account_for_recurring.id,
        ),
    )

    with _with_ahead():
        count1 = await generate_pending(session, test_user.id, up_to=date(2025, 12, 1))
    assert count1 == 2  # Dec 1 (due) + Jan 1 (ahead)
    assert [r.date for r in await _generated_rows(session, "Steady Sub")] == [
        date(2025, 12, 1),
        date(2026, 1, 1),
    ]

    # Steady state: run on Jan 1 with next_occurrence already at Feb 1.
    with _with_ahead():
        count2 = await generate_pending(session, test_user.id, up_to=date(2026, 1, 1))
    assert count2 == 1  # only Feb 1 (ahead); Jan is already materialized
    rows = await _generated_rows(session, "Steady Sub")
    assert [r.date for r in rows] == [
        date(2025, 12, 1),
        date(2026, 1, 1),
        date(2026, 2, 1),
    ]
    assert all(r.status == "pending" for r in rows)

    await session.refresh(rec)
    # next_occurrence stays at Feb 1 (next actual due date)
    assert rec.next_occurrence == date(2026, 2, 1)


@pytest.mark.asyncio
async def test_generate_pending_ahead_no_runaway_between_occurrences(
    session: AsyncSession, test_user, test_workspace, test_account_for_recurring
):
    """Flag ON: a run between occurrence dates must not keep pulling the
    pointer forward. After the steady state, a cutoff that is not an
    occurrence date leaves next_occurrence (the next due date) alone
    until the next occurrence date arrives."""
    rec = await create_recurring_transaction(
        session,
        test_workspace.id, test_user.id,
        RecurringTransactionCreate(
            description="NoRunaway Sub",
            amount=Decimal("9"),
            type="debit",
            frequency="monthly",
            start_date=date(2025, 12, 1),
            account_id=test_account_for_recurring.id,
        ),
    )

    with _with_ahead():
        await generate_pending(session, test_user.id, up_to=date(2025, 12, 1))
        # Between occurrences: next is Jan 1 (next actual due date, already
        # materialized as ahead row).
        count = await generate_pending(session, test_user.id, up_to=date(2025, 12, 10))

    assert count == 0
    assert len(await _generated_rows(session, "NoRunaway Sub")) == 2
    await session.refresh(rec)
    # next_occurrence stays at Jan 1 (next actual due date)
    assert rec.next_occurrence == date(2026, 1, 1)


@pytest.mark.asyncio
async def test_generate_pending_ahead_day_of_month_one_period_ahead(
    session: AsyncSession, test_user, test_workspace, test_account_for_recurring
):
    """Flag ON: a day-15 bill materializes its nearest upcoming occurrence one
    period ahead — Jan 15 on the Jan 1 run, Feb 15 on the Jan 15 run — and a
    run in between does not advance it further."""
    rec = await create_recurring_transaction(
        session,
        test_workspace.id, test_user.id,
        RecurringTransactionCreate(
            description="Mid Month Sub",
            amount=Decimal("20"),
            type="debit",
            frequency="monthly",
            day_of_month=15,
            start_date=date(2026, 1, 15),
            account_id=test_account_for_recurring.id,
        ),
    )

    # Cutoff Jan 1: Jan 15 is the first occurrence after the cutoff.
    with _with_ahead():
        count1 = await generate_pending(session, test_user.id, up_to=date(2026, 1, 1))
    assert count1 == 1
    assert [r.date for r in await _generated_rows(session, "Mid Month Sub")] == [
        date(2026, 1, 15)
    ]
    await session.refresh(rec)
    # next_occurrence stays at Jan 15 (next actual due date)
    assert rec.next_occurrence == date(2026, 1, 15)

    # Cutoff Jan 15: Feb 15 is now the nearest upcoming occurrence.
    with _with_ahead():
        count2 = await generate_pending(session, test_user.id, up_to=date(2026, 1, 15))
    assert count2 == 1
    assert [r.date for r in await _generated_rows(session, "Mid Month Sub")] == [
        date(2026, 1, 15),
        date(2026, 2, 15),
    ]
    await session.refresh(rec)
    # next_occurrence stays at Feb 15 (next actual due date)
    assert rec.next_occurrence == date(2026, 2, 15)

    # Cutoff Jan 20: nothing new until Feb 15 arrives.
    with _with_ahead():
        count3 = await generate_pending(session, test_user.id, up_to=date(2026, 1, 20))
    assert count3 == 0


@pytest.mark.asyncio
async def test_generate_pending_previous_friday_uses_effective_cutoff_and_date(
    session: AsyncSession, test_user, test_workspace, test_account_for_recurring
):
    rec = await create_recurring_transaction(
        session,
        test_workspace.id,
        test_user.id,
        RecurringTransactionCreate(
            description="Weekend rent",
            amount=Decimal("1000"),
            type="debit",
            frequency="monthly",
            start_date=date(2026, 8, 1),
            weekend_adjustment="previous_friday",
            account_id=test_account_for_recurring.id,
        ),
    )

    assert await generate_pending(session, test_user.id, up_to=date(2026, 7, 31)) == 1
    transaction = (
        await session.execute(
            select(Transaction).where(Transaction.recurring_transaction_id == rec.id)
        )
    ).scalar_one()
    assert transaction.date == date(2026, 7, 31)
    await session.refresh(rec)
    assert rec.next_occurrence == date(2026, 9, 1)


@pytest.mark.asyncio
async def test_generate_pending_next_monday_waits_until_effective_date(
    session: AsyncSession, test_user, test_workspace, test_account_for_recurring
):
    rec = await create_recurring_transaction(
        session,
        test_workspace.id,
        test_user.id,
        RecurringTransactionCreate(
            description="Weekend salary",
            amount=Decimal("2000"),
            type="credit",
            frequency="monthly",
            start_date=date(2026, 8, 2),
            weekend_adjustment="next_monday",
            account_id=test_account_for_recurring.id,
        ),
    )

    assert await generate_pending(session, test_user.id, up_to=date(2026, 8, 2)) == 0
    await session.refresh(rec)
    assert rec.next_occurrence == date(2026, 8, 2)

    assert await generate_pending(session, test_user.id, up_to=date(2026, 8, 3)) == 1
    transaction = (
        await session.execute(
            select(Transaction).where(Transaction.recurring_transaction_id == rec.id)
        )
    ).scalar_one()
    assert transaction.date == date(2026, 8, 3)
    await session.refresh(rec)
    assert rec.next_occurrence == date(2026, 9, 2)


@pytest.mark.asyncio
async def test_generate_pending_weekend_adjustment_respects_nominal_end_date(
    session: AsyncSession, test_user, test_workspace, test_account_for_recurring
):
    rec = await create_recurring_transaction(
        session,
        test_workspace.id,
        test_user.id,
        RecurringTransactionCreate(
            description="Final weekend bill",
            amount=Decimal("50"),
            type="debit",
            frequency="monthly",
            start_date=date(2026, 8, 1),
            end_date=date(2026, 8, 1),
            weekend_adjustment="previous_friday",
            account_id=test_account_for_recurring.id,
        ),
    )

    assert await generate_pending(session, test_user.id, up_to=date(2026, 7, 31)) == 1
    assert await generate_pending(session, test_user.id, up_to=date(2026, 12, 31)) == 0
    result = await session.execute(
        select(Transaction).where(Transaction.recurring_transaction_id == rec.id)
    )
    assert [transaction.date for transaction in result.scalars()] == [date(2026, 7, 31)]
    await session.refresh(rec)
    assert rec.next_occurrence == date(2026, 9, 1)
    assert rec.is_active is False
