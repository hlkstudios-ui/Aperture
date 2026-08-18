import hashlib
import re
import secrets
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.auth import DbSession, require_customer_session, require_trusted_origin
from app.catalog_models import Movie
from app.club_models import (
    ClubCollection,
    ClubDiscussionPost,
    ClubMembership,
    ClubMembershipStatus,
    ClubPoll,
    ClubPollOption,
    ClubPollVote,
    ClubRole,
    ClubScheduledWatch,
    ClubWatchHistory,
    ClubWatchStatus,
    MovieClub,
    PartyEventKind,
    PartyState,
    WatchParty,
    WatchPartyEvent,
    WatchPartyMessage,
    WatchPartyParticipant,
)
from app.club_schemas import (
    ClubCreate,
    ClubJoin,
    ClubListWrite,
    ClubResponse,
    DiscussionWrite,
    MembershipWrite,
    PartyControl,
    PartyCreate,
    PartyHeartbeat,
    PartyJoin,
    PartyMessageWrite,
    PartyResponse,
    PollCreate,
    ScheduleCreate,
    VoteWrite,
)
from app.curation_models import Collection, CollectionKind
from app.curation_service import collection_response, load_collection
from app.feature_flags import require_watch_parties
from app.geo import OptionalViewerCountry
from app.models import DeviceSession, PlaybackSource, Profile
from app.rate_limit import enforce_rate_limit
from app.routes.community import hidden_profile_ids
from app.routes.playback import config_for, playable_source
from app.routes.recommendations import active_profile
from app.scheduling import availability_clause

router = APIRouter(
    prefix="/clubs",
    tags=["movie clubs and watch parties"],
    dependencies=[Depends(require_trusted_origin)],
)
CurrentSession = Annotated[DeviceSession, Depends(require_customer_session)]


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def membership(db: DbSession, club_id: uuid.UUID, profile_id: uuid.UUID) -> ClubMembership:
    record = db.scalar(
        select(ClubMembership).where(
            ClubMembership.club_id == club_id,
            ClubMembership.profile_id == profile_id,
            ClubMembership.status == ClubMembershipStatus.active,
        )
    )
    if record is None:
        raise HTTPException(404, "Club was not found")
    return record


def manage_membership(db: DbSession, club_id: uuid.UUID, profile_id: uuid.UUID) -> ClubMembership:
    record = membership(db, club_id, profile_id)
    if record.role not in {ClubRole.owner, ClubRole.moderator}:
        raise HTTPException(403, "Club moderator access is required")
    return record


def club_record(db: DbSession, club_id: uuid.UUID) -> MovieClub:
    club = db.scalar(
        select(MovieClub).options(selectinload(MovieClub.members)).where(MovieClub.id == club_id)
    )
    if club is None:
        raise HTTPException(404, "Club was not found")
    return club


def club_response(
    db: DbSession,
    club: MovieClub,
    profile_id: uuid.UUID,
    invite_token: str | None = None,
    country: str | None = None,
) -> ClubResponse:
    own_membership = membership(db, club.id, profile_id)
    hidden = hidden_profile_ids(db, profile_id)
    members = []
    for item in club.members:
        if item.status == ClubMembershipStatus.active and item.profile_id not in hidden:
            name = db.scalar(select(Profile.name).where(Profile.id == item.profile_id))
            members.append(
                {"profile_id": str(item.profile_id), "name": name, "role": item.role.value}
            )
    watches = db.scalars(
        select(ClubScheduledWatch)
        .join(Movie, ClubScheduledWatch.movie_id == Movie.id)
        .where(
            ClubScheduledWatch.club_id == club.id,
            availability_clause(Movie, country=country),
        )
        .order_by(ClubScheduledWatch.scheduled_at.desc())
    ).all()
    polls = []
    for poll in db.scalars(
        select(ClubPoll)
        .options(selectinload(ClubPoll.options))
        .where(ClubPoll.club_id == club.id)
        .order_by(ClubPoll.created_at.desc())
    ):
        polls.append(
            {
                "id": str(poll.id),
                "question": poll.question,
                "closes_at": poll.closes_at,
                "options": [
                    {
                        "id": str(option.id),
                        "label": option.label,
                        "votes": db.scalar(
                            select(func.count(ClubPollVote.id)).where(
                                ClubPollVote.option_id == option.id
                            )
                        ),
                    }
                    for option in poll.options
                ],
            }
        )
    posts = []
    for post in db.scalars(
        select(ClubDiscussionPost)
        .where(ClubDiscussionPost.club_id == club.id, ClubDiscussionPost.removed_at.is_(None))
        .order_by(ClubDiscussionPost.created_at.desc())
        .limit(100)
    ):
        if post.profile_id not in hidden:
            posts.append(
                {
                    "id": str(post.id),
                    "profile_id": str(post.profile_id),
                    "profile_name": db.scalar(
                        select(Profile.name).where(Profile.id == post.profile_id)
                    ),
                    "body": post.body,
                    "contains_spoilers": post.contains_spoilers,
                    "created_at": post.created_at,
                }
            )
    lists = []
    for link in db.scalars(select(ClubCollection).where(ClubCollection.club_id == club.id)):
        collection = db.get(Collection, link.collection_id)
        if collection:
            lists.append(
                collection_response(db, load_collection(db, collection.id), country).model_dump(
                    mode="json"
                )
            )
    history = [
        {
            "scheduled_watch_id": str(item.scheduled_watch_id),
            "profile_id": str(item.profile_id),
            "joined_at": item.joined_at,
            "completed": item.completed,
        }
        for item in db.scalars(
            select(ClubWatchHistory)
            .join(ClubScheduledWatch)
            .where(ClubScheduledWatch.club_id == club.id)
            .order_by(ClubWatchHistory.joined_at.desc())
        )
    ]
    return ClubResponse(
        id=club.id,
        slug=club.slug,
        name=club.name,
        description=club.description,
        role=own_membership.role.value,
        members=members,
        scheduled_watches=[
            {
                "id": str(item.id),
                "movie_id": str(item.movie_id),
                "playback_source_id": str(item.playback_source_id)
                if item.playback_source_id
                else None,
                "title": item.title,
                "scheduled_at": item.scheduled_at,
                "status": item.status.value,
            }
            for item in watches
        ],
        polls=polls,
        discussion=posts,
        lists=lists,
        watch_history=history,
        invite_token=invite_token,
    )


@router.post("", response_model=ClubResponse, status_code=status.HTTP_201_CREATED)
async def create_club(
    payload: ClubCreate,
    db: DbSession,
    session: CurrentSession,
    country: OptionalViewerCountry,
) -> ClubResponse:
    profile = active_profile(db, session)
    await enforce_rate_limit(f"clubs:create:{profile.id}", limit=5, window_seconds=86400)
    token = secrets.token_urlsafe(32)
    stem = re.sub(r"[^a-z0-9]+", "-", payload.name.lower()).strip("-")[:140] or "club"
    club = MovieClub(
        owner_profile_id=profile.id,
        slug=f"{stem}-{uuid.uuid4().hex[:10]}",
        name=payload.name,
        description=payload.description,
        invite_token_hash=digest(token),
    )
    db.add(club)
    db.flush()
    db.add(
        ClubMembership(
            club_id=club.id,
            profile_id=profile.id,
            role=ClubRole.owner,
            status=ClubMembershipStatus.active,
            joined_at=datetime.now(UTC),
        )
    )
    db.commit()
    return club_response(db, club_record(db, club.id), profile.id, token, country)


@router.post("/join", response_model=ClubResponse)
async def join_club(
    payload: ClubJoin,
    db: DbSession,
    session: CurrentSession,
    country: OptionalViewerCountry,
) -> ClubResponse:
    profile = active_profile(db, session)
    await enforce_rate_limit(f"clubs:join:{profile.id}", limit=20, window_seconds=3600)
    club = db.scalar(
        select(MovieClub).where(MovieClub.invite_token_hash == digest(payload.invite_token))
    )
    if club is None:
        raise HTTPException(404, "Club invitation is invalid")
    record = db.scalar(
        select(ClubMembership).where(
            ClubMembership.club_id == club.id, ClubMembership.profile_id == profile.id
        )
    )
    if record is None:
        db.add(
            ClubMembership(
                club_id=club.id,
                profile_id=profile.id,
                role=ClubRole.member,
                status=ClubMembershipStatus.active,
                joined_at=datetime.now(UTC),
            )
        )
    else:
        record.status, record.joined_at = ClubMembershipStatus.active, datetime.now(UTC)
    db.commit()
    return club_response(db, club_record(db, club.id), profile.id, country=country)


@router.get("", response_model=list[ClubResponse])
def my_clubs(
    db: DbSession, session: CurrentSession, country: OptionalViewerCountry
) -> list[ClubResponse]:
    profile = active_profile(db, session)
    ids = db.scalars(
        select(ClubMembership.club_id).where(
            ClubMembership.profile_id == profile.id,
            ClubMembership.status == ClubMembershipStatus.active,
        )
    )
    return [
        club_response(db, club_record(db, club_id), profile.id, country=country) for club_id in ids
    ]


@router.get("/{club_id}", response_model=ClubResponse)
def get_club(
    club_id: uuid.UUID,
    db: DbSession,
    session: CurrentSession,
    country: OptionalViewerCountry,
) -> ClubResponse:
    profile = active_profile(db, session)
    membership(db, club_id, profile.id)
    return club_response(db, club_record(db, club_id), profile.id, country=country)


@router.put("/{club_id}/members/{member_profile_id}", response_model=ClubResponse)
def update_member(
    club_id: uuid.UUID,
    member_profile_id: uuid.UUID,
    payload: MembershipWrite,
    db: DbSession,
    session: CurrentSession,
    country: OptionalViewerCountry,
) -> ClubResponse:
    profile = active_profile(db, session)
    actor = manage_membership(db, club_id, profile.id)
    target = membership(db, club_id, member_profile_id)
    if target.role == ClubRole.owner:
        raise HTTPException(409, "The club owner cannot be changed or removed")
    if actor.role != ClubRole.owner and (
        target.role == ClubRole.moderator or payload.role != ClubRole.member
    ):
        raise HTTPException(403, "Only the club owner can manage moderators")
    if payload.role == ClubRole.owner:
        raise HTTPException(422, "Ownership transfer is not supported")
    target.role = payload.role
    target.status = payload.status
    db.commit()
    return club_response(db, club_record(db, club_id), profile.id, country=country)


@router.post("/{club_id}/schedule", response_model=ClubResponse)
async def schedule_watch(
    club_id: uuid.UUID,
    payload: ScheduleCreate,
    db: DbSession,
    session: CurrentSession,
    country: OptionalViewerCountry,
) -> ClubResponse:
    profile = active_profile(db, session)
    manage_membership(db, club_id, profile.id)
    await enforce_rate_limit(f"clubs:schedule:{profile.id}", limit=20, window_seconds=3600)
    movie = db.scalar(
        select(Movie).where(
            Movie.id == payload.movie_id,
            availability_clause(Movie, country=country),
        )
    )
    source_id = payload.playback_source_id or db.scalar(
        select(PlaybackSource.id).where(PlaybackSource.movie_id == payload.movie_id).limit(1)
    )
    source = playable_source(db, source_id or uuid.uuid4(), country)
    if movie is None or source.movie_id != movie.id:
        raise HTTPException(422, "Choose an available source assigned to this movie")
    db.add(
        ClubScheduledWatch(
            club_id=club_id,
            movie_id=movie.id,
            playback_source_id=source.id,
            created_by_profile_id=profile.id,
            title=payload.title,
            scheduled_at=payload.scheduled_at,
        )
    )
    db.commit()
    return club_response(db, club_record(db, club_id), profile.id, country=country)


@router.post("/{club_id}/polls", response_model=ClubResponse)
async def create_poll(
    club_id: uuid.UUID,
    payload: PollCreate,
    db: DbSession,
    session: CurrentSession,
    country: OptionalViewerCountry,
) -> ClubResponse:
    profile = active_profile(db, session)
    manage_membership(db, club_id, profile.id)
    await enforce_rate_limit(f"clubs:poll:{profile.id}", limit=20, window_seconds=3600)
    poll = ClubPoll(
        club_id=club_id,
        created_by_profile_id=profile.id,
        question=payload.question,
        closes_at=payload.closes_at,
    )
    db.add(poll)
    db.flush()
    for position, option in enumerate(payload.options):
        db.add(ClubPollOption(poll_id=poll.id, position=position, **option.model_dump()))
    db.commit()
    return club_response(db, club_record(db, club_id), profile.id, country=country)


@router.put("/{club_id}/polls/{poll_id}/vote", response_model=ClubResponse)
def vote(
    club_id: uuid.UUID,
    poll_id: uuid.UUID,
    payload: VoteWrite,
    db: DbSession,
    session: CurrentSession,
    country: OptionalViewerCountry,
) -> ClubResponse:
    profile = active_profile(db, session)
    membership(db, club_id, profile.id)
    poll = db.scalar(select(ClubPoll).where(ClubPoll.id == poll_id, ClubPoll.club_id == club_id))
    option = db.scalar(
        select(ClubPollOption).where(
            ClubPollOption.id == payload.option_id, ClubPollOption.poll_id == poll_id
        )
    )
    if poll is None or option is None or (poll.closes_at and poll.closes_at <= datetime.now(UTC)):
        raise HTTPException(422, "Poll is unavailable")
    record = db.scalar(
        select(ClubPollVote).where(
            ClubPollVote.poll_id == poll_id, ClubPollVote.profile_id == profile.id
        )
    )
    if record:
        record.option_id = option.id
    else:
        db.add(ClubPollVote(poll_id=poll_id, option_id=option.id, profile_id=profile.id))
    db.commit()
    return club_response(db, club_record(db, club_id), profile.id, country=country)


@router.post("/{club_id}/discussion", response_model=ClubResponse)
async def post_discussion(
    club_id: uuid.UUID,
    payload: DiscussionWrite,
    db: DbSession,
    session: CurrentSession,
    country: OptionalViewerCountry,
) -> ClubResponse:
    profile = active_profile(db, session)
    membership(db, club_id, profile.id)
    await enforce_rate_limit(f"clubs:discussion:{profile.id}", limit=30, window_seconds=3600)
    db.add(ClubDiscussionPost(club_id=club_id, profile_id=profile.id, **payload.model_dump()))
    db.commit()
    return club_response(db, club_record(db, club_id), profile.id, country=country)


@router.delete("/{club_id}/discussion/{post_id}", response_model=ClubResponse)
def remove_discussion(
    club_id: uuid.UUID,
    post_id: uuid.UUID,
    db: DbSession,
    session: CurrentSession,
    country: OptionalViewerCountry,
) -> ClubResponse:
    profile = active_profile(db, session)
    actor = membership(db, club_id, profile.id)
    post = db.scalar(
        select(ClubDiscussionPost).where(
            ClubDiscussionPost.id == post_id, ClubDiscussionPost.club_id == club_id
        )
    )
    if post is None:
        raise HTTPException(404, "Discussion post was not found")
    if post.profile_id != profile.id and actor.role not in {ClubRole.owner, ClubRole.moderator}:
        raise HTTPException(403, "Only the author or a club moderator can remove this post")
    post.removed_at = datetime.now(UTC)
    db.commit()
    return club_response(db, club_record(db, club_id), profile.id, country=country)


@router.post("/{club_id}/lists", response_model=ClubResponse)
def add_club_list(
    club_id: uuid.UUID,
    payload: ClubListWrite,
    db: DbSession,
    session: CurrentSession,
    country: OptionalViewerCountry,
) -> ClubResponse:
    profile = active_profile(db, session)
    manage_membership(db, club_id, profile.id)
    collection = db.get(Collection, payload.collection_id)
    if (
        collection is None
        or collection.kind != CollectionKind.user_list
        or collection.owner_profile_id != profile.id
    ):
        raise HTTPException(404, "List was not found")
    if not db.scalar(
        select(ClubCollection.id).where(
            ClubCollection.club_id == club_id, ClubCollection.collection_id == collection.id
        )
    ):
        db.add(
            ClubCollection(
                club_id=club_id, collection_id=collection.id, added_by_profile_id=profile.id
            )
        )
        db.commit()
    return club_response(db, club_record(db, club_id), profile.id, country=country)


def party_record(db: DbSession, party_id: uuid.UUID) -> WatchParty:
    party = db.get(WatchParty, party_id)
    if party is None:
        raise HTTPException(404, "Watch party was not found")
    return party


def authorize_party(db: DbSession, party: WatchParty, session: DeviceSession, country: str | None):
    profile = active_profile(db, session)
    source = playable_source(db, party.playback_source_id, country)
    config = config_for(db, source, session, country)
    scheduled = db.get(ClubScheduledWatch, party.scheduled_watch_id)
    membership(db, scheduled.club_id, profile.id)
    return profile, config


def party_response(
    db: DbSession,
    party: WatchParty,
    client_position: float | None = None,
    client_revision: int | None = None,
    access_token: str | None = None,
) -> PartyResponse:
    now = datetime.now(UTC)
    effective = party.position_seconds + (
        (now - party.state_changed_at).total_seconds() if party.state == PartyState.playing else 0
    )
    correction = (client_revision is not None and client_revision != party.revision) or (
        client_position is not None and abs(client_position - effective) > 2
    )
    participants = [
        {
            "profile_id": str(item.profile_id),
            "profile_name": db.scalar(select(Profile.name).where(Profile.id == item.profile_id)),
            "joined_at": item.joined_at,
            "left_at": item.left_at,
        }
        for item in db.scalars(
            select(WatchPartyParticipant).where(
                WatchPartyParticipant.party_id == party.id, WatchPartyParticipant.left_at.is_(None)
            )
        )
    ]
    messages = [
        {
            "id": str(item.id),
            "profile_id": str(item.profile_id),
            "profile_name": db.scalar(select(Profile.name).where(Profile.id == item.profile_id)),
            "kind": item.kind.value,
            "body": item.body,
            "created_at": item.created_at,
        }
        for item in db.scalars(
            select(WatchPartyMessage)
            .where(WatchPartyMessage.party_id == party.id)
            .order_by(WatchPartyMessage.created_at.desc())
            .limit(100)
        )
    ]
    source = db.get(PlaybackSource, party.playback_source_id)
    movie = db.get(Movie, source.movie_id) if source and source.movie_id else None
    return PartyResponse(
        id=party.id,
        scheduled_watch_id=party.scheduled_watch_id,
        playback_source_id=party.playback_source_id,
        host_profile_id=party.host_profile_id,
        state=party.state,
        position_seconds=party.position_seconds,
        effective_position_seconds=max(0, effective),
        revision=party.revision,
        server_time=now,
        state_changed_at=party.state_changed_at,
        correction_required=correction,
        seek_to_seconds=effective if correction else None,
        participants=participants,
        messages=messages,
        access_token=access_token,
        watch_href=f"/watch/movies/{movie.slug}" if movie else "/",
    )


@router.post(
    "/{club_id}/parties",
    response_model=PartyResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_watch_parties)],
)
def create_party(
    club_id: uuid.UUID,
    payload: PartyCreate,
    db: DbSession,
    session: CurrentSession,
    country: OptionalViewerCountry,
) -> PartyResponse:
    profile = active_profile(db, session)
    manage_membership(db, club_id, profile.id)
    scheduled = db.scalar(
        select(ClubScheduledWatch).where(
            ClubScheduledWatch.id == payload.scheduled_watch_id,
            ClubScheduledWatch.club_id == club_id,
        )
    )
    if scheduled is None or scheduled.playback_source_id is None:
        raise HTTPException(422, "Scheduled watch has no playable source")
    if db.scalar(select(WatchParty.id).where(WatchParty.scheduled_watch_id == scheduled.id)):
        raise HTTPException(409, "This scheduled watch already has a party")
    source = playable_source(db, scheduled.playback_source_id, country)
    config_for(db, source, session, country)
    token = secrets.token_urlsafe(32)
    party = WatchParty(
        scheduled_watch_id=scheduled.id,
        playback_source_id=source.id,
        host_profile_id=profile.id,
        access_token_hash=digest(token),
    )
    db.add(party)
    db.flush()
    db.add(
        WatchPartyParticipant(
            party_id=party.id, profile_id=profile.id, entitlement_verified_at=datetime.now(UTC)
        )
    )
    db.add(ClubWatchHistory(scheduled_watch_id=scheduled.id, profile_id=profile.id))
    db.commit()
    return party_response(db, party, access_token=token)


@router.post(
    "/parties/{party_id}/join",
    response_model=PartyResponse,
    dependencies=[Depends(require_watch_parties)],
)
async def join_party(
    party_id: uuid.UUID,
    payload: PartyJoin,
    db: DbSession,
    session: CurrentSession,
    country: OptionalViewerCountry,
) -> PartyResponse:
    party = party_record(db, party_id)
    if party.state == PartyState.ended:
        raise HTTPException(409, "This watch party has ended")
    if not secrets.compare_digest(party.access_token_hash, digest(payload.access_token)):
        raise HTTPException(404, "Watch party invitation is invalid")
    profile, _ = authorize_party(db, party, session, country)
    await enforce_rate_limit(f"party:join:{profile.id}", limit=30, window_seconds=3600)
    participant = db.scalar(
        select(WatchPartyParticipant).where(
            WatchPartyParticipant.party_id == party.id,
            WatchPartyParticipant.profile_id == profile.id,
        )
    )
    now = datetime.now(UTC)
    if participant:
        participant.left_at = None
        participant.last_seen_at = now
        participant.entitlement_verified_at = now
    else:
        db.add(
            WatchPartyParticipant(
                party_id=party.id, profile_id=profile.id, entitlement_verified_at=now
            )
        )
    history = db.scalar(
        select(ClubWatchHistory).where(
            ClubWatchHistory.scheduled_watch_id == party.scheduled_watch_id,
            ClubWatchHistory.profile_id == profile.id,
        )
    )
    if history is None:
        db.add(ClubWatchHistory(scheduled_watch_id=party.scheduled_watch_id, profile_id=profile.id))
    db.commit()
    return party_response(db, party)


@router.get(
    "/parties/{party_id}",
    response_model=PartyResponse,
    dependencies=[Depends(require_watch_parties)],
)
def party_state(
    party_id: uuid.UUID,
    db: DbSession,
    session: CurrentSession,
    country: OptionalViewerCountry,
) -> PartyResponse:
    party = party_record(db, party_id)
    profile, _ = authorize_party(db, party, session, country)
    participant = db.scalar(
        select(WatchPartyParticipant).where(
            WatchPartyParticipant.party_id == party.id,
            WatchPartyParticipant.profile_id == profile.id,
            WatchPartyParticipant.left_at.is_(None),
        )
    )
    if participant is None:
        raise HTTPException(404, "Watch party was not found")
    participant.last_seen_at = datetime.now(UTC)
    participant.entitlement_verified_at = datetime.now(UTC)
    db.commit()
    return party_response(db, party)


@router.post(
    "/parties/{party_id}/control",
    response_model=PartyResponse,
    dependencies=[Depends(require_watch_parties)],
)
def control_party(
    party_id: uuid.UUID,
    payload: PartyControl,
    db: DbSession,
    session: CurrentSession,
    country: OptionalViewerCountry,
) -> PartyResponse:
    party = party_record(db, party_id)
    profile, config = authorize_party(db, party, session, country)
    if party.host_profile_id != profile.id:
        raise HTTPException(403, "Only the host can control playback")
    if party.revision != payload.expected_revision:
        raise HTTPException(409, "Party state changed; refresh before controlling playback")
    if payload.position_seconds > config.duration_seconds + 1:
        raise HTTPException(422, "Party position exceeds the source duration")
    party.revision += 1
    party.position_seconds = payload.position_seconds
    party.state_changed_at = datetime.now(UTC)
    party.state = {
        PartyEventKind.play: PartyState.playing,
        PartyEventKind.pause: PartyState.paused,
        PartyEventKind.seek: party.state,
        PartyEventKind.ended: PartyState.ended,
    }[payload.kind]
    if payload.kind == PartyEventKind.ended:
        scheduled = db.get(ClubScheduledWatch, party.scheduled_watch_id)
        if scheduled:
            scheduled.status = ClubWatchStatus.completed
        for item in db.scalars(
            select(ClubWatchHistory).where(
                ClubWatchHistory.scheduled_watch_id == party.scheduled_watch_id
            )
        ):
            item.completed = True
    db.add(
        WatchPartyEvent(
            party_id=party.id,
            actor_profile_id=profile.id,
            kind=payload.kind,
            position_seconds=payload.position_seconds,
            revision=party.revision,
        )
    )
    db.commit()
    return party_response(db, party)


@router.post(
    "/parties/{party_id}/heartbeat",
    response_model=PartyResponse,
    dependencies=[Depends(require_watch_parties)],
)
def heartbeat(
    party_id: uuid.UUID,
    payload: PartyHeartbeat,
    db: DbSession,
    session: CurrentSession,
    country: OptionalViewerCountry,
) -> PartyResponse:
    party = party_record(db, party_id)
    profile, _ = authorize_party(db, party, session, country)
    participant = db.scalar(
        select(WatchPartyParticipant).where(
            WatchPartyParticipant.party_id == party.id,
            WatchPartyParticipant.profile_id == profile.id,
            WatchPartyParticipant.left_at.is_(None),
        )
    )
    if participant is None:
        raise HTTPException(404, "Watch party was not found")
    participant.last_seen_at = datetime.now(UTC)
    participant.entitlement_verified_at = datetime.now(UTC)
    db.commit()
    return party_response(
        db, party, payload.client_position_seconds, client_revision=payload.expected_revision
    )


@router.post(
    "/parties/{party_id}/messages",
    response_model=PartyResponse,
    dependencies=[Depends(require_watch_parties)],
)
async def party_message(
    party_id: uuid.UUID,
    payload: PartyMessageWrite,
    db: DbSession,
    session: CurrentSession,
    country: OptionalViewerCountry,
) -> PartyResponse:
    party = party_record(db, party_id)
    profile, _ = authorize_party(db, party, session, country)
    participant = db.scalar(
        select(WatchPartyParticipant.id).where(
            WatchPartyParticipant.party_id == party.id,
            WatchPartyParticipant.profile_id == profile.id,
            WatchPartyParticipant.left_at.is_(None),
        )
    )
    if participant is None:
        raise HTTPException(404, "Watch party was not found")
    await enforce_rate_limit(f"party:message:{profile.id}", limit=60, window_seconds=60)
    db.add(WatchPartyMessage(party_id=party.id, profile_id=profile.id, **payload.model_dump()))
    db.commit()
    return party_response(db, party)


@router.delete(
    "/parties/{party_id}/leave",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_watch_parties)],
)
def leave_party(
    party_id: uuid.UUID,
    db: DbSession,
    session: CurrentSession,
    country: OptionalViewerCountry,
) -> Response:
    party = party_record(db, party_id)
    profile, _ = authorize_party(db, party, session, country)
    if party.host_profile_id == profile.id and party.state != PartyState.ended:
        raise HTTPException(409, "Host must end the party before leaving")
    participant = db.scalar(
        select(WatchPartyParticipant).where(
            WatchPartyParticipant.party_id == party.id,
            WatchPartyParticipant.profile_id == profile.id,
        )
    )
    if participant:
        participant.left_at = datetime.now(UTC)
        db.commit()
    return Response(status_code=204)
