from typing import Tuple, Dict, List
import logging
from datetime import datetime
import pytz
from lxml import objectify

from kloppy.domain import (
    EventDataset,
    Team,
    Period,
    Point,
    BallState,
    DatasetFlag,
    Orientation,
    PitchDimensions,
    Dimension,
    PassEvent,
    ShotEvent,
    TakeOnEvent,
    CarryEvent,
    GenericEvent,
    PassResult,
    ShotResult,
    TakeOnResult,
    CarryResult,
    EventType,
    Ground,
    Score,
    Provider,
    Metadata,
    Player,
    Position,
)
from kloppy.infra.serializers.event import EventDataSerializer
from kloppy.infra.utils import Readable, performance_logging

logger = logging.getLogger(__name__)


def _parse_f24_datetime(dt_str: str) -> float:
    return (
        datetime.strptime(dt_str, "%Y-%m-%dT%H:%M:%S.%f")
        .replace(tzinfo=pytz.utc)
        .timestamp()
    )


def _parse_pass(qualifiers: Dict[int, str], outcome: int) -> Dict:
    if outcome:
        receiver_coordinates = Point(
            x=float(qualifiers[140]), y=float(qualifiers[141])
        )
        result = PassResult.COMPLETE
    else:
        result = PassResult.INCOMPLETE
        receiver_coordinates = None

    return dict(
        result=result,
        receiver_coordinates=receiver_coordinates,
        receiver_player=None,
        receive_timestamp=None,
    )


def _parse_offside_pass() -> Dict:
    return dict(
        result=PassResult.OFFSIDE,
        receiver_coordinates=None,
        receiver_player=None,
        receive_timestamp=None,
    )


def _parse_take_on(outcome: int) -> Dict:
    if outcome:
        result = TakeOnResult.COMPLETE
    else:
        result = TakeOnResult.INCOMPLETE
    return dict(result=result)


def _parse_shot(
    qualifiers: Dict[int, str], type_id: int, coordinates: Point
) -> Dict:
    if type_id == EVENT_TYPE_SHOT_GOAL:
        if 28 in qualifiers:
            coordinates = Point(x=100 - coordinates.x, y=100 - coordinates.y)
        result = ShotResult.GOAL
    else:
        result = None

    return dict(coordinates=coordinates, result=result)


def _parse_team_players(
    f7_root, team_ref: str
) -> Tuple[str, Dict[str, Dict[str, str]]]:
    matchdata_path = objectify.ObjectPath("SoccerFeed.SoccerDocument")
    team_elms = list(matchdata_path.find(f7_root).iterchildren("Team"))
    for team_elm in team_elms:
        if team_elm.attrib["uID"] == team_ref:
            team_name = str(team_elm.find("Name"))
            players = {
                player_elm.attrib["uID"]: dict(
                    first_name=str(
                        player_elm.find("PersonName").find("First")
                    ),
                    last_name=str(player_elm.find("PersonName").find("Last")),
                )
                for player_elm in team_elm.iterchildren("Player")
            }
            break
    else:
        raise Exception(f"Could not parse players for {team_ref}")

    return team_name, players


def _team_from_xml_elm(team_elm, f7_root) -> Team:
    # This should not happen here
    team_name, team_players = _parse_team_players(
        f7_root, team_elm.attrib["TeamRef"]
    )

    team_id = team_elm.attrib["TeamRef"].lstrip("t")
    team = Team(
        team_id=str(team_id),
        name=team_name,
        ground=Ground.HOME
        if team_elm.attrib["Side"] == "Home"
        else Ground.AWAY,
    )
    team.players = [
        Player(
            player_id=player_elm.attrib["PlayerRef"].lstrip("p"),
            team=team,
            jersey_no=int(player_elm.attrib["ShirtNumber"]),
            first_name=team_players[player_elm.attrib["PlayerRef"]][
                "first_name"
            ],
            last_name=team_players[player_elm.attrib["PlayerRef"]][
                "last_name"
            ],
            position=Position(
                position_id=player_elm.attrib["Formation_Place"],
                name=player_elm.attrib["Position"],
                coordinates=None,
            ),
        )
        for player_elm in team_elm.find("PlayerLineUp").iterchildren(
            "MatchPlayer"
        )
    ]
    return team


EVENT_TYPE_START_PERIOD = 32
EVENT_TYPE_END_PERIOD = 30

EVENT_TYPE_PASS = 1
EVENT_TYPE_OFFSIDE_PASS = 1
EVENT_TYPE_TAKE_ON = 3
EVENT_TYPE_SHOT_MISS = 13
EVENT_TYPE_SHOT_POST = 14
EVENT_TYPE_SHOT_SAVED = 15
EVENT_TYPE_SHOT_GOAL = 16

event_type_names = {
    1: "pass",
    2: "offside pass",
    3: "take on",
    4: "foul",
    5: "out",
    6: "corner awarded",
    7: "tackle",
    8: "interception",
    9: "turnover",
    10: "save",
    11: "claim",
    12: "clearance",
    13: "miss",
    14: "post",
    15: "attempt saved",
    16: "goal",
    17: "card",
    18: "player off",
    19: "player on",
    20: "player retired",
    21: "player returns",
    22: "player becomes goalkeeper",
    23: "goalkeeper becomes player",
    24: "condition change",
    25: "official change",
    26: "unknown26",
    27: "start delay",
    28: "end delay",
    29: "unknown29",
    30: "end",
    31: "unknown31",
    32: "start",
    33: "unknown33",
    34: "team set up",
    35: "player changed position",
    36: "player changed jersey number",
    37: "collection end",
    38: "temp_goal",
    39: "temp_attempt",
    40: "formation change",
    41: "punch",
    42: "good skill",
    43: "deleted event",
    44: "aerial",
    45: "challenge",
    46: "unknown46",
    47: "rescinded card",
    48: "unknown46",
    49: "ball recovery",
    50: "dispossessed",
    51: "error",
    52: "keeper pick-up",
    53: "cross not claimed",
    54: "smother",
    55: "offside provoked",
    56: "shield ball opp",
    57: "foul throw in",
    58: "penalty faced",
    59: "keeper sweeper",
    60: "chance missed",
    61: "ball touch",
    62: "unknown62",
    63: "temp_save",
    64: "resume",
    65: "contentious referee decision",
    66: "possession data",
    67: "50/50",
    68: "referee drop ball",
    69: "failed to block",
    70: "injury time announcement",
    71: "coach setup",
    72: "caught offside",
    73: "other ball contact",
    74: "blocked pass",
    75: "delayed start",
    76: "early end",
    77: "player off pitch",
}

BALL_OWNING_EVENTS = (1, 2, 3, 13, 14, 15, 16, 49)


def _get_event_type_name(type_id: int) -> str:
    return event_type_names.get(type_id, "unknown")


class OptaSerializer(EventDataSerializer):
    @staticmethod
    def __validate_inputs(inputs: Dict[str, Readable]):
        if "f7_data" not in inputs:
            raise ValueError("Please specify a value for input 'f7_data'")
        if "f24_data" not in inputs:
            raise ValueError("Please specify a value for input 'f24_data'")

    def deserialize(
        self, inputs: Dict[str, Readable], options: Dict = None
    ) -> EventDataset:
        """
                Deserialize Opta event data into a `EventDataset`.

                Parameters
                ----------
                inputs : dict
                    input `f24_data` should point to a `Readable` object containing
                    the 'xml' formatted event data. input `f7_data` should point
                    to a `Readable` object containing the 'xml' formatted f7 data.
                options : dict
                    Options for deserialization of the Opta file. Possible options are
                    `event_types` (list of event types) to specify the event types that
                    should be returned. Valid types: "shot", "pass", "carry", "take_on" and
                    "generic". Generic is everything other than the first 4. Those events
                    are barely parsed. This type of event can be used to do the parsing
                    yourself.
                    Every event has a 'raw_event' attribute which contains the original
                    dictionary.
                Returns
                -------
                dataset : EventDataset
                Raises
                ------

                See Also
                --------

                Examples
                --------
                >>> serializer = OptaSerializer()
                >>> with open("123_f24.xml", "rb") as f24_data, \
                >>>      open("123_f7.xml", "rb") as f7_data:
                >>>
                >>>     dataset = serializer.deserialize(
                >>>         inputs={
                >>>             'f24_data': f24_data,
                >>>             'f7_data': f7_data
                >>>         },
                >>>         options={
                >>>             'event_types': ["pass", "take_on", "carry", "shot"]
                >>>         }
                >>>     )
                """
        self.__validate_inputs(inputs)
        if not options:
            options = {}

        with performance_logging("load data", logger=logger):
            f7_root = objectify.fromstring(inputs["f7_data"].read())
            f24_root = objectify.fromstring(inputs["f24_data"].read())

            wanted_event_types = [
                EventType[event_type.upper()]
                for event_type in options.get("event_types", [])
            ]

        with performance_logging("parse data", logger=logger):
            matchdata_path = objectify.ObjectPath(
                "SoccerFeed.SoccerDocument.MatchData"
            )
            team_elms = list(
                matchdata_path.find(f7_root).iterchildren("TeamData")
            )

            home_score = None
            away_score = None
            for team_elm in team_elms:
                if team_elm.attrib["Side"] == "Home":
                    home_score = team_elm.attrib["Score"]
                    home_team = _team_from_xml_elm(team_elm, f7_root)
                elif team_elm.attrib["Side"] == "Away":
                    away_score = team_elm.attrib["Score"]
                    away_team = _team_from_xml_elm(team_elm, f7_root)
                else:
                    raise Exception(f"Unknown side: {team_elm.attrib['Side']}")

            score = Score(home=home_score, away=away_score)
            teams = [home_team, away_team]

            if len(home_team.players) == 0 or len(away_team.players) == 0:
                raise Exception("LineUp incomplete")

            game_elm = f24_root.find("Game")
            periods = [
                Period(id=1, start_timestamp=None, end_timestamp=None,),
                Period(id=2, start_timestamp=None, end_timestamp=None,),
            ]
            possession_team = None
            events = []
            for event_elm in game_elm.iterchildren("Event"):
                event_id = event_elm.attrib["id"]
                type_id = int(event_elm.attrib["type_id"])
                timestamp = _parse_f24_datetime(event_elm.attrib["timestamp"])
                period_id = int(event_elm.attrib["period_id"])
                for period in periods:
                    if period.id == period_id:
                        break
                else:
                    logger.debug(
                        f"Skipping event {event_id} because period doesn't match {period_id}"
                    )
                    continue

                if type_id == EVENT_TYPE_START_PERIOD:
                    logger.debug(
                        f"Set start of period {period.id} to {timestamp}"
                    )
                    period.start_timestamp = timestamp
                elif type_id == EVENT_TYPE_END_PERIOD:
                    logger.debug(
                        f"Set end of period {period.id} to {timestamp}"
                    )
                    period.end_timestamp = timestamp
                else:
                    if not period.start_timestamp:
                        # not started yet
                        continue

                    if event_elm.attrib["team_id"] == home_team.team_id:
                        team = teams[0]
                    elif event_elm.attrib["team_id"] == away_team.team_id:
                        team = teams[1]
                    else:
                        raise Exception(
                            f"Unknown team_id {event_elm.attrib['team_id']}"
                        )

                    x = float(event_elm.attrib["x"])
                    y = float(event_elm.attrib["y"])
                    outcome = int(event_elm.attrib["outcome"])
                    qualifiers = {
                        int(
                            qualifier_elm.attrib["qualifier_id"]
                        ): qualifier_elm.attrib.get("value")
                        for qualifier_elm in event_elm.iterchildren("Q")
                    }
                    player = None
                    if "player_id" in event_elm.attrib:
                        player = team.get_player_by_id(
                            event_elm.attrib["player_id"]
                        )

                    if type_id in BALL_OWNING_EVENTS:
                        possession_team = team

                    generic_event_kwargs = dict(
                        # from DataRecord
                        period=period,
                        timestamp=timestamp - period.start_timestamp,
                        ball_owning_team=possession_team,
                        ball_state=BallState.ALIVE,
                        # from Event
                        event_id=event_id,
                        team=team,
                        player=player,
                        coordinates=Point(x=x, y=y),
                        raw_event=event_elm,
                    )

                    if type_id == EVENT_TYPE_PASS:
                        pass_event_kwargs = _parse_pass(qualifiers, outcome)
                        event = PassEvent(
                            **pass_event_kwargs, **generic_event_kwargs,
                        )
                    elif type_id == EVENT_TYPE_OFFSIDE_PASS:
                        pass_event_kwargs = _parse_offside_pass()
                        event = PassEvent(
                            **pass_event_kwargs, **generic_event_kwargs,
                        )
                    elif type_id == EVENT_TYPE_TAKE_ON:
                        take_on_event_kwargs = _parse_take_on(outcome)
                        event = TakeOnEvent(
                            **take_on_event_kwargs, **generic_event_kwargs,
                        )
                    elif type_id in (
                        EVENT_TYPE_SHOT_MISS,
                        EVENT_TYPE_SHOT_POST,
                        EVENT_TYPE_SHOT_SAVED,
                        EVENT_TYPE_SHOT_GOAL,
                    ):
                        shot_event_kwargs = _parse_shot(
                            qualifiers,
                            type_id,
                            coordinates=generic_event_kwargs["coordinates"],
                        )
                        kwargs = {}
                        kwargs.update(generic_event_kwargs)
                        kwargs.update(shot_event_kwargs)
                        event = ShotEvent(**kwargs)
                    else:
                        event = GenericEvent(
                            **generic_event_kwargs,
                            result=None,
                            event_name=_get_event_type_name(type_id),
                        )

                    if (
                        not wanted_event_types
                        or event.event_type in wanted_event_types
                    ):
                        events.append(event)

        metadata = Metadata(
            teams=teams,
            periods=periods,
            pitch_dimensions=PitchDimensions(
                x_dim=Dimension(0, 100), y_dim=Dimension(0, 100)
            ),
            score=score,
            frame_rate=None,
            orientation=Orientation.ACTION_EXECUTING_TEAM,
            flags=DatasetFlag.BALL_OWNING_TEAM,
            provider=Provider.OPTA,
        )

        return EventDataset(metadata=metadata, records=events,)

    def serialize(self, data_set: EventDataset) -> Tuple[str, str]:
        raise NotImplementedError
