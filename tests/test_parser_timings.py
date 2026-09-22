import pytest
import datetime
from lark.exceptions import VisitError, UnexpectedCharacters, UnexpectedToken
from resource_flow.parser import RecipeParser, DateParseError
from resource_flow.models import TravelEdge, ShoppingHeuristic, WorkWindow

@pytest.fixture
def parser():
    return RecipeParser()

def test_comment_at_start(parser):
    code = "-- This is a comment\nmake 1 cake;"
    ctx = parser.parse_string(code, "test.rf")
    assert len(ctx.query.query) == 1

def test_comment_after_code(parser):
    code = "make 1 cake; -- This is another comment"
    ctx = parser.parse_string(code, "test.rf")
    assert len(ctx.query.query) == 1

def test_map_block(parser):
    code = '''
    map {
        Home <-> Lidl : 15 min;
        supplier Lidl [shopping_time: 5 min + 1 min / item];
        supplier Rewe [shopping_time: 10 min];
        supplier Aldi [shopping_time: 2 min / item];
    }
    make 1 cake;
    '''
    ctx = parser.parse_string(code, "test.rf")
    assert len(ctx.map_block.edges) == 1
    assert ctx.map_block.edges[0].loc_a == "Home"
    assert ctx.map_block.edges[0].loc_b == "Lidl"
    assert ctx.map_block.edges[0].time.val == 15
    assert ctx.map_block.edges[0].time.unit == "min"

    assert len(ctx.map_block.heuristics) == 3
    assert ctx.map_block.heuristics[0].supplier == "Lidl"
    assert ctx.map_block.heuristics[0].base_time.val == 5
    assert ctx.map_block.heuristics[0].per_item_time.val == 1

    assert ctx.map_block.heuristics[1].supplier == "Rewe"
    assert ctx.map_block.heuristics[1].base_time.val == 10
    assert ctx.map_block.heuristics[1].per_item_time.val == 0

    assert ctx.map_block.heuristics[2].supplier == "Aldi"
    assert ctx.map_block.heuristics[2].base_time.val == 0
    assert ctx.map_block.heuristics[2].per_item_time.val == 2

def test_calendar_block(parser):
    code = '''
    calendar {
        work 17:00 to 20:00;
        work Saturday 10:00 to 18:00;
    }
    make 1 cake;
    '''
    ctx = parser.parse_string(code, "test.rf")
    assert len(ctx.calendar_block.windows) == 2
    
    w1 = ctx.calendar_block.windows[0]
    assert w1.day_of_week is None
    assert w1.start_time.hour == 17
    assert w1.start_time.minute == 0
    assert w1.end_time.hour == 20

    w2 = ctx.calendar_block.windows[1]
    assert w2.day_of_week == "Saturday"
    assert w2.start_time.hour == 10
    assert w2.end_time.hour == 18

def test_make_starting_only(parser):
    code = "make 1 cake starting Monday 08:00;"
    ctx = parser.parse_string(code, "test.rf")
    assert ctx.query.start_time is not None
    assert ctx.query.start_time.year == 2024
    assert ctx.query.start_time.month == 1
    assert ctx.query.start_time.day == 1 # 2024-01-01 is a Monday
    assert ctx.query.start_time.hour == 8

def test_make_by_only(parser):
    code = "make 1 cake by 18:00;"
    with pytest.raises(VisitError) as excinfo:
        parser.parse_string(code, "test.rf")
    assert isinstance(excinfo.value.orig_exc, DateParseError)
    assert "starting point must be provided" in str(excinfo.value.orig_exc)

def test_make_at_starting_by(parser):
    code = "make 1 cake at Home starting Monday 08:00 by 18:00;"
    ctx = parser.parse_string(code, "test.rf")
    assert ctx.query.location == "Home"
    assert ctx.query.start_time is not None
    assert ctx.query.start_time.day == 1
    assert ctx.query.start_time.hour == 8
    assert ctx.query.deadline is not None
    assert ctx.query.deadline.day == 1
    assert ctx.query.deadline.hour == 18

def test_smart_date_inference_weekday(parser):
    code = "make 1 cake starting Monday 08:00 by Tuesday 18:00;"
    ctx = parser.parse_string(code, "test.rf")
    assert ctx.query.deadline.day == 2 # Tuesday is the next day
    assert ctx.query.deadline.hour == 18

def test_smart_date_inference_today(parser):
    # Test that when a starting point has no day, it uses the base day, and deadline uses same day
    code = "make 1 cake starting 08:00 by 18:00;"
    ctx = parser.parse_string(code, "test.rf")
    assert ctx.query.start_time.day == 1
    assert ctx.query.start_time.hour == 8
    assert ctx.query.deadline.day == 1
    assert ctx.query.deadline.hour == 18

def test_smart_date_inference_tomorrow(parser):
    # Test that when deadline time is before start time, it rolls over to next day
    code = "make 1 cake starting Monday 18:00 by 08:00;"
    ctx = parser.parse_string(code, "test.rf")
    assert ctx.query.start_time.day == 1
    assert ctx.query.start_time.hour == 18
    assert ctx.query.deadline.day == 2
    assert ctx.query.deadline.hour == 8

def test_invalid_date_format(parser):
    code = "make 1 cake by NotADate;"
    with pytest.raises(VisitError) as excinfo:
        parser.parse_string(code, "test.rf")
    assert isinstance(excinfo.value.orig_exc, DateParseError)

def test_invalid_map_edge(parser):
    code = '''
    map {
        Home -> Lidl : 15 min;
    }
    '''
    with pytest.raises((UnexpectedToken, UnexpectedCharacters)):
        parser.parse_string(code, "test.rf")

def test_missing_calendar_brackets(parser):
    code = '''
    calendar 
        work 17:00 to 20:00;
    '''
    with pytest.raises((UnexpectedToken, UnexpectedCharacters)):
        parser.parse_string(code, "test.rf")
