import datetime
import re
from collections.abc import Iterator
from typing import Optional

import click

from .config import Config
from .data import load_frames, Day, Calendar, Weekday

DEFAULT_PERIOD = datetime.timedelta(days=7)
SECS_PER_HOUR = 60 * 60

def print_total_compact(total: datetime.timedelta):
    units = [(60, 'm'), (60, 'h'), (24, 'd'), (365, 'y')]
    ret_unit = 's'
    value = abs(total.total_seconds())
    for factor, unit in units:
        if value > 60:
            ret_unit = unit
            value = value / factor
        else:
            break
    return f'{round(value, 2)}{ret_unit}'

def print_total_exact(total: datetime.timedelta, hours_per_day: datetime.timedelta):
    full_workdays = 0
    remainder = abs(total)

    while remainder > hours_per_day:
        remainder -= hours_per_day
        full_workdays += 1

    if full_workdays > 0:
        return f'{full_workdays} Workdays and {remainder}'
    else:
        return f'{remainder}'

def print_total(config: Config, total: datetime.timedelta):
    if config.total_format() == 'exact':
        return print_total_exact(total, config.worktime_per_day())
    else:
        return print_total_compact(total)

class Date(click.ParamType):
    name = "date"

    def convert(self, value, param, ctx):
        if value is None:
            return None

        if isinstance(value, Date):
            return value

        return datetime.date.fromisoformat(value)


class TimeDelta(click.ParamType):
    name = "period"

    def convert(self, value, param, ctx):
        if value is None:
            return None

        if isinstance(value, TimeDelta):
            return value

        matcher = re.compile(r"^(((?P<days>\d+)\s*d(ays)?))|((?P<weeks>\d+)\s*w(eeks)?)$")
        match = matcher.match(value)

        if not match:
            self.fail("Invalid period", param, ctx)

        result = datetime.timedelta()
        if match.group("days"):
            result += datetime.timedelta(days=int(match.group("days")))
        if match.group("weeks"):
            result += datetime.timedelta(days=7*int(match.group("weeks")))
        return result


@click.group()
@click.pass_context
def cli(ctx):
    ctx.obj = Config()
    ctx.obj.load()


@cli.group("vacation")
def vacation():
    pass


@vacation.command("list")
@click.pass_context
def vacation_list(ctx: click.Context):
    """Lists the vacation days that watson-worktime knows about."""
    config: Config = ctx.obj
    days = list(config.vacation())
    days.sort()
    for day in days:
        echo_date = click.style(day.strftime("%Y-%m-%d"), fg="cyan", bold=True)
        click.echo(echo_date)

    current_days = [day for day in days if day.year == datetime.datetime.now().year]
    click.echo("------")
    echo_taken = click.style(f"Vacation days taken: {len(current_days)}", fg="green", bold=True)
    echo_remaining = click.style(f"Vacation days remaining: {config.vacation_per_year() - len(current_days)}", fg="yellow", bold=True)
    click.echo(echo_taken)
    click.echo(echo_remaining)

@vacation.command("add")
@click.option("--from", "from_", type=Date(), help="Start day of vacation")
@click.option("--to", type=Date(), help="End day of vacation")
@click.argument("day", nargs=-1, type=Date())
@click.pass_context
def vacation_add(
    ctx: click.Context,
    day: list[datetime.date],
    from_: Optional[datetime.date],
    to: Optional[datetime.date],
):
    """Adds a vacation day."""
    config: Config = ctx.obj
    frames = load_frames(include_current=False)
    calendar = Calendar(frames)

    day = list(day)

    if from_ is not None and to is not None:
        try:
            period_start, period_end = get_period(config, from_, to, None, False)
        except ValueError as exc:
            ctx.fail(str(exc))

        for date in iterdays(period_start, period_end):
            cur_day = calendar[date]
            # We use show_day as a heuristic to decide whether we should add
            # the day as a vacation day. This way we automatically ignore
            # holidays and non-work days.
            if show_day(cur_day, config):
                day.append(cur_day.get_date())
    elif from_ or to:
        ctx.fail("Need both, --from and --to!")

    for vacation_day in day:
        config.add_vacation(vacation_day)
    config.save()


@vacation.command("del")
@click.option("--from", "from_", type=Date(), help="Start day of vacation")
@click.option("--to", type=Date(), help="End day of vacation")
@click.argument("day", nargs=-1, type=Date())
@click.pass_context
def vacation_del(
    ctx: click.Context,
    day: list[datetime.date],
    from_: Optional[datetime.date],
    to: Optional[datetime.date],
):
    """Deletes a vacation day."""
    config: Config = ctx.obj
    day = list(day)

    if from_ is not None and to is not None:
        try:
            period_start, period_end = get_period(config, from_, to, None, False)
        except ValueError as exc:
            ctx.fail(str(exc))
        day.extend(iterdays(period_start, period_end))
    elif from_ or to:
        ctx.fail("Need both, --from and --to!")

    for vacation_day in day:
        try:
            config.remove_vacation(vacation_day)
        except KeyError:
            pass
    config.save()


@cli.command("report")
@click.option("--from", "from_", type=Date(), help="Start day to report")
@click.option("--to", type=Date(), help="End day to report")
@click.option("--period", type=TimeDelta(), help="Period to report")
@click.option("--workweek", is_flag=True, help="Show the current workweek")
@click.option("--current", "-c", is_flag=True, help="Include the current frame")
@click.pass_context
def report(
    ctx: click.Context,
    from_: Optional[datetime.date],
    to: Optional[datetime.date],
    period: Optional[datetime.timedelta],
    workweek: bool,
    current: bool,
):
    """Reports the worktime (and overtime) for the given time period."""
    config: Config = ctx.obj
    frames = load_frames(include_current=current)
    calendar = Calendar(frames)

    try:
        period_start, period_end = get_period(config, from_, to, period, workweek)
    except ValueError as exc:
        ctx.fail(str(exc))

    total_overtime = datetime.timedelta(0)

    for date in iterdays(period_start, period_end):
        day = calendar[date]
        if not show_day(day, config):
            continue

        echo_name = click.style(day.date.strftime("%a"), fg="cyan")
        echo_date = click.style(day.date.strftime("%Y-%m-%d"), fg="cyan", bold=True)
        echo_worktime = click.style(str(day.worktime), fg="green")

        expected = day.expected_worktime(config)
        overtime = day.worktime - expected
        if day.worktime == expected:
            echo_overtime = "+0"
        elif day.worktime > expected:
            echo_overtime = click.style("+" + str(overtime), fg="yellow")
        else:
            echo_overtime = click.style("-" + str(abs(overtime)), fg="red")
        total_overtime += overtime
        click.echo(f"Day {echo_name} {echo_date}: {echo_worktime} {echo_overtime}")

    if total_overtime > datetime.timedelta(0):
        echo_total = click.style("+" + print_total(config, total_overtime), fg="yellow")
    else:
        echo_total = click.style("-" + print_total(config, total_overtime), fg="red")
    click.echo("------")
    click.echo(f"Total: {echo_total}")


def get_period(
    config: Config,
    from_: Optional[datetime.date],
    to: Optional[datetime.date],
    period: Optional[datetime.timedelta],
    workweek: bool,
) -> tuple[datetime.date, datetime.date]:
    if workweek:
        if from_ or to:
            raise ValueError("Cannot give --from/--to when using --workweek")

        first_dow = config.workdays()[0]
        period_end = datetime.date.today()
        period_start = period_end
        while Weekday.from_date(period_start) != first_dow:
            period_start -= datetime.timedelta(days=1)

    else:
        if from_ is not None and to is not None and period is not None:
            raise ValueError("Cannot give all of --from, --to and --period")
        period_end = to or datetime.date.today()
        if from_ is not None:
            period_start = from_
        elif period is not None:
            period_start = period_end - period
        elif config.inception():
            period_start = config.inception()
        else:
            period_start = period_end - DEFAULT_PERIOD
    return (period_start, period_end)


def iterdays(start: datetime.date, stop: datetime.date) -> Iterator[datetime.date]:
    current = start
    while current <= stop:
        yield current
        current += datetime.timedelta(days=1)


def show_day(day: Day, config: Config) -> bool:
    """Determines whether the given day should be shown."""
    # Always show days on which work has been done
    if day.worktime:
        return True

    # Hide days on which we're not expected to work
    if not day.expected_worktime(config):
        return False

    return True


__all__ = ["cli", "report"]
