# COMMAND A — MASTER PRODUCT, ARCHITECTURE, AND ACCEPTANCE BLUEPRINT

## 0. Authority of This File

This file is the **authoritative product and architecture specification** for the streaming-platform project.

Codex must treat this document as the source of truth for:
- product vision,
- customer experience,
- administrator experience,
- system architecture,
- video-processing requirements,
- feature scope,
- quality expectations,
- live-development expectations,
- security requirements,
- testing expectations,
- production-readiness gates,
- and the final definition of done.

Do **not** reduce this project to a minimum viable Netflix clone.

The target is an **exceptional streaming platform for movie enthusiasts**: a product that combines premium streaming, deep movie discovery, scene-level intelligence, personal film history, social/cinephile tools, and a powerful single-admin publishing studio.

---

# 1. North-Star Product Goal

Build a production-grade streaming platform that answers:

> **Everything a movie fan could want to watch, understand, remember, discover, organize, revisit, and discuss about a film — without leaving the platform.**

The product must serve two very different users equally well:

### Normal Viewer
A simple, beautiful, fast streaming experience:
- open the site,
- discover something,
- press Play,
- continue watching,
- search,
- save titles,
- manage an account,
- watch on desktop/mobile,
- and never feel overwhelmed.

### Cinephile / Movie Enthusiast
An optional deep mode that turns every movie into an explorable knowledge universe:
- spoiler-safe scene intelligence,
- character recognition and reminders,
- relationship graphs,
- filmmaking details,
- notes and bookmarks,
- alternate editions,
- film journeys,
- personal statistics,
- deep discovery,
- reviews,
- knowledge graphs,
- and structured post-watch exploration.

The site must therefore expose two experience modes:

1. **Normal Mode**
2. **Cinephile Mode**

Both operate on the same catalog and account.

---

# 2. Mandatory Live-Development Goal

Development must be visible while it is happening.

## 2.1 Required Behavior

As soon as the application skeleton is functional:

- start the frontend development server;
- start the backend API server;
- start the required local infrastructure;
- enable hot reload;
- keep the site running throughout development whenever technically possible;
- verify every major implementation step in the browser;
- do not declare a UI feature complete merely because the source code compiles.

Default development URLs:

- Customer application: `http://localhost:3000`
- Admin Studio: `http://localhost:3000/studio`
- Backend API: `http://localhost:8000`
- API documentation: `http://localhost:8000/docs`
- Object-storage console if used locally: document its URL in `docs/DEVELOPMENT.md`

If the existing repository already uses other ports or architecture, preserve the existing convention unless there is a strong reason to change it.

## 2.2 Live Preview Is an Acceptance Gate

After every customer-facing or admin-facing milestone:

1. build/compile,
2. run automated tests,
3. open the relevant page in a browser,
4. verify the expected state,
5. check browser console errors,
6. check failed network requests,
7. verify responsive behavior,
8. record the result in the project status log.

A feature that cannot be demonstrated in the running application is **not complete**.

## 2.3 Optional Shared Staging Preview

When deployment credentials/infrastructure are available, maintain a staging environment so the owner can view development remotely.

Staging must:
- use non-production data,
- never expose development secrets,
- use protected admin authentication,
- use separate storage/database resources,
- and remain isolated from production.

---

# 3. Product Boundaries

The system consists of three major products sharing one platform.

## A. Customer Streaming Experience
Public-facing subscriber/viewer product.

## B. Private Admin Studio
A private content-management, publishing, operations, and analytics system.

There is exactly **one administrator**.

There must be:
- no public admin registration,
- no staff marketplace,
- no creator accounts,
- no editor roles,
- no moderator hierarchy,
- no publisher role system,
- no creator revenue-share tooling unless explicitly added later.

## C. Streaming and Intelligence Infrastructure
The backend, databases, media pipelines, recommendations, search, scene intelligence, analytics, storage, transcoding, delivery, observability, and security layer.

---

# 4. Customer Application — Global Experience

## 4.1 Main Navigation

Desktop navigation should support, where applicable:

- Logo
- Home
- Movies
- Series
- New & Popular
- Collections
- Film Journeys
- Search
- My List
- Cinema Passport
- Profile / Account

Cinephile Mode may expose:
- Discover
- Knowledge Graph
- Film Journeys
- Reviews / Community
- Saved Scenes / Notes

Mobile navigation must be redesigned appropriately rather than shrinking the desktop navigation.

---

# 5. Customer Homepage

The homepage should feel cinematic, fast, responsive, and highly visual.

## 5.1 Hero Area

Support:
- featured movie/series,
- hero artwork,
- optional background video/trailer,
- title logo,
- short description,
- metadata,
- Play / Resume,
- My List,
- More Info,
- sound toggle,
- age rating,
- quality badges where relevant.

## 5.2 Content Rails

Support horizontal content rails/collections such as:

- Continue Watching
- Trending Now
- Popular
- Top 10
- Recently Added
- New Releases
- New Episodes
- Recommended For You
- Because You Watched...
- Movies
- Series
- Anime
- Documentary
- Comedy
- Action
- Drama
- Horror
- Science Fiction
- Family
- Coming Soon
- Editor's Picks
- Award Winners
- Seasonal Collections
- Franchise Collections
- Director Collections
- Country / Era / Movement collections

The admin must be able to control editorial rails from the Admin Studio.

---

# 6. Content Cards

Cards must be reusable interactive components.

Support:
- poster artwork,
- landscape artwork,
- title,
- release year,
- runtime,
- age rating,
- quality badges,
- episode metadata,
- progress indicator,
- new-content badge,
- subtitle/dub indicators when relevant,
- hover/focus preview on capable devices,
- Play,
- Resume,
- Add/Remove My List,
- Like/Dislike or rating interaction,
- More Information,
- trailer/preview,
- keyboard accessibility,
- touch-friendly behavior.

Do not depend on hover for essential functionality.

---

# 7. Movie Detail Experience

A movie detail page/modal should support:

- cinematic backdrop,
- optional trailer,
- title logo,
- Play / Resume,
- My List,
- rating interaction,
- release year,
- runtime,
- age/certification,
- supported video quality,
- HDR/Dolby/etc. metadata where available,
- synopsis,
- genres,
- themes/tags,
- cast,
- director,
- writers,
- cinematographer,
- editor,
- composer,
- production company/studio,
- countries,
- languages,
- trailers,
- teasers,
- clips,
- related titles,
- franchise links,
- editions/cuts,
- related collections,
- "More Like This",
- spoiler-safe entry into SceneLens,
- post-watch material when unlocked.

---

# 8. Series / Anime Experience

Data hierarchy:

```text
Series
 ├── Season
 │    ├── Episode
 │    ├── Episode
 │    └── Episode
 └── Specials
```

Series pages must support:
- season selector,
- episode list,
- episode thumbnails,
- title,
- description,
- runtime,
- watch progress,
- watched indicator,
- resume,
- next episode,
- new episode badge,
- air/release date,
- audio languages,
- subtitle languages,
- dub/sub indicators,
- specials,
- trailers,
- related series/movies.

Anime-oriented support should include:
- original-language track,
- dubbed audio tracks,
- multiple subtitle tracks,
- subtitle preference persistence,
- clear episode/season numbering,
- support for specials/OVAs or equivalent content groupings.

---

# 9. Video Player

The player is a core product, not a generic HTML video element.

## 9.1 Required Controls

- Play / Pause
- Seek
- Scrubber
- Volume
- Mute
- Fullscreen
- Picture-in-Picture where supported
- Keyboard shortcuts
- Playback speed
- Quality selection
- Auto quality
- Subtitle selection
- Audio selection
- Subtitle appearance controls
- Episode selector
- Next Episode
- Autoplay next episode
- Skip Intro
- Skip Recap
- Skip Credits
- Resume playback
- Loading/buffering states
- Error recovery
- Media-session integration where applicable

## 9.2 Quality

Support adaptive renditions such as:
- 360p
- 480p
- 720p
- 1080p
- optional 1440p
- optional 4K

Actual exposed options depend on source media and account/plan policy.

## 9.3 Accessibility

Support:
- closed captions,
- subtitles,
- audio descriptions if supplied,
- keyboard navigation,
- screen-reader labeling,
- high-contrast/focus behavior,
- resizable captions,
- subtitle background/position preferences where feasible.

## 9.4 Exceptional Player Features

- Dual-subtitle mode where licensed subtitle tracks exist
- Dialogue-focus audio mode where technically possible and source-compatible
- Scene bookmarks
- Personal scene notes
- SceneLens
- Ask This Movie
- "Who Was That?"
- "What Did I Miss?"
- relationship map
- scene-aware music information
- scene-aware filmmaking information
- spoiler-safe easter eggs / production notes

---

# 10. Watch Progress and Resume

Persist watch progress robustly.

Example logical data:
- user/profile id,
- media id,
- playback position,
- duration,
- percentage,
- last-watched timestamp,
- completed state,
- last episode,
- device/session context where appropriate.

Requirements:
- resume from last valid position,
- Continue Watching rail,
- remove near-completed titles using configurable threshold,
- mark episodes/movies completed,
- sync across devices,
- avoid excessive database writes through sensible batching/throttling.

---

# 11. Search and Discovery

Search must go beyond title matching.

Index/search:
- title,
- alternate/original title,
- synopsis,
- cast,
- director,
- writers,
- cinematographer,
- composer,
- studio,
- genres,
- themes,
- tags,
- characters,
- franchise,
- country,
- language,
- year,
- collections.

Support:
- autocomplete,
- typo tolerance,
- recent searches,
- trending searches,
- faceted filters,
- sort options,
- empty-state suggestions,
- search-history controls.

Advanced discovery should allow natural filters such as:
- decade,
- country,
- runtime,
- director,
- actor,
- genre,
- mood,
- theme,
- availability,
- language,
- rating,
- watched/unwatched,
- edition.

---

# 12. Movie Prescription — "One Perfect Movie"

Build an intentional discovery system that solves endless browsing.

Inputs may include:
- time available,
- mood,
- dark/light,
- serious/fun,
- slow/fast,
- comforting/intense,
- preferred genres,
- unwanted genres,
- release era,
- language,
- subtitle needs,
- who the viewer is watching with,
- new watch vs rewatch,
- quality preference,
- desired emotional/visual qualities.

Output should support:
- one recommended title,
- taste-match score,
- concise explanation,
- constraint satisfaction,
- Play,
- Another Recommendation.

Do not fabricate explanations. Explanations must be derived from real catalog/user signals.

---

# 13. Taste DNA

Build a transparent preference model for each profile.

Potential dimensions:
- directors,
- actors,
- writers,
- cinematographers,
- composers,
- genres,
- themes,
- narrative style,
- pacing,
- mood,
- ending style,
- runtime tolerance,
- decades,
- countries,
- languages,
- franchises,
- film movements,
- viewing time,
- completion behavior,
- rewatches,
- user ratings,
- watchlist behavior.

Expose understandable insights rather than only a black-box recommendation score.

Examples:
- favorite directors,
- strongest genre affinities,
- preferred eras,
- slow-burn tolerance,
- nonlinear storytelling affinity,
- dark-atmosphere preference,
- average runtime enjoyed.

---

# 14. Recommendation System

Start with reliable explainable logic, then evolve.

Initial signals:
- genre similarity,
- tags/themes,
- cast/crew overlap,
- franchise,
- editorial curation,
- popularity,
- recency,
- profile watch history,
- ratings,
- completion,
- rewatches,
- My List additions.

Later:
- collaborative filtering,
- embeddings,
- sequence-aware recommendations,
- context-aware recommendations,
- session/mood intent,
- diversity/novelty controls.

Every recommendation system must include:
- fallback behavior for new users,
- cold-start handling for new titles,
- explainability where shown,
- diversity controls,
- avoidance of repetitive rails.

---

# 15. No-Algorithm Mode

Give the viewer control.

Homepage mode options may include:
- Personalized
- Curated
- Chronological
- Critics
- Friends
- Random Discovery
- No Algorithm

No Algorithm mode should expose deterministic browsing such as:
- Recently Added
- A-Z
- Release Year
- Director
- Country
- Genre
- Collection

Personalization settings must be explicit and reversible.

---

# 16. SceneLens — Flagship Feature

SceneLens is a primary differentiator.

When the viewer pauses or invokes SceneLens, the platform may present information about the exact moment being watched.

## 16.1 Spoiler Boundary

If playback is at timestamp `T`, spoiler-safe answers may use:
- information before `T`,
- information at `T`,
- catalog/global non-spoiler metadata,
- approved non-spoiler production information.

They must **not reveal story information from timestamps after `T`** unless the user deliberately disables spoiler protection.

This rule applies to:
- AI answers,
- character descriptions,
- relationship maps,
- scene explanations,
- easter eggs,
- foreshadowing explanations,
- plot reminders.

## 16.2 SceneLens Modules

Potential modules:
- current characters,
- actor identity,
- previous appearances,
- spoiler-safe character summary,
- relationship graph,
- "What just happened?"
- "Why is this important?" without future spoilers,
- music/score cue,
- production notes,
- filming location,
- cinematography data,
- editing notes,
- visual-effects notes,
- references/easter eggs,
- continuity details,
- credits,
- scene bookmark,
- personal note.

## 16.3 Ask This Movie

Users can ask natural-language questions such as:
- "Who is this person?"
- "Have I seen this character before?"
- "What did they say about this earlier?"
- "What is this character trying to do?"
- "What did I miss?"
- "Why did the aspect ratio change?"

Answers must:
- use the current spoiler boundary,
- distinguish fact from inference,
- cite/source internal metadata where appropriate,
- decline to invent unavailable information.

---

# 17. "Who Was That?"

One-tap character reminder:
- character name,
- actor,
- first appearance,
- prior appearances,
- spoiler-safe known relationships,
- spoiler-safe summary up to current timestamp.

Useful for:
- ensemble films,
- mysteries,
- long series,
- films revisited after a break.

---

# 18. "What Did I Miss?"

Generate a concise recap between:
- a prior remembered timestamp,
- and the current timestamp,

or from the beginning to the current timestamp.

Must not expose anything later than the viewer's current spoiler boundary.

---

# 19. Dynamic Character Relationship Map

Build a graph that can evolve with progress.

Nodes:
- characters,
- groups,
- organizations,
- locations if useful.

Edges:
- family,
- friendship,
- conflict,
- alliance,
- employment,
- known association,
- other verified relationships.

Only reveal relationships known by the current playback timestamp when spoiler protection is on.

---

# 20. Scene Bookmarks, Notes, and Frame Gallery

Allow users to:
- bookmark a scene,
- title a bookmark,
- add private notes,
- organize bookmarks,
- revisit scenes where rights/streaming rules permit,
- attach notes to timestamps,
- build a personal visual memory/gallery based on permitted thumbnails/stills.

Do not allow mechanisms intended to defeat content protections or redistribute copyrighted footage.

---

# 21. Music Timeline

Where licensed metadata exists, map:
- song,
- score cue,
- composer,
- performer,
- soundtrack entry,
- timestamp/scene.

Do not display copyrighted lyrics unless separately licensed.

---

# 22. Filmmaking Explorer

Where reliable metadata is available, expose:
- director,
- cinematographer,
- editor,
- production designer,
- composer,
- aspect ratio,
- capture format,
- lens/camera information where verified,
- filming location,
- production notes,
- VFX notes,
- color/presentation notes.

Unknown data must remain unknown rather than being guessed.

---

# 23. Easter Egg / Production-Note Mode

Provide:
- references,
- verified easter eggs,
- production trivia,
- continuity notes,
- filmmaking observations.

Spoiler protection must apply.

---

# 24. Commentary Mode

Support licensed commentary tracks or synchronized commentary when rights exist.

Potential tracks:
- director,
- cast,
- cinematographer,
- critic/scholar,
- production team.

Do not assume commentary rights.

---

# 25. Edition Vault

Where licensed, support multiple versions of a title:
- theatrical cut,
- director's cut,
- extended cut,
- restoration,
- alternate audio,
- alternate presentation.

Each edition needs:
- separate media asset/version,
- runtime,
- edition metadata,
- availability/rights window,
- associated subtitles/audio,
- comparison metadata.

---

# 26. Version Comparison

When multiple licensed editions exist, show:
- runtime differences,
- inserted/removed scenes,
- presentation changes,
- restoration information,
- audio differences,
- verified editorial differences.

Avoid spoilers before completion unless explicitly enabled.

---

# 27. Original Presentation Mode

For film purists:
- preserve intended aspect ratio,
- preserve frame rate where appropriate,
- expose verified presentation metadata,
- avoid forced cropping,
- avoid destructive stretching,
- support original-language default,
- expose restoration/source information where known.

---

# 28. Credits Explorer

Credits are first-class discovery objects.

Users should be able to open:
- actor,
- director,
- writer,
- cinematographer,
- editor,
- composer,
- production designer,
- studio/company.

Then discover all catalog titles connected to that person/company.

---

# 29. Film Knowledge Graph / Film Family Tree

Build navigable relationships between:
- films,
- sequels,
- prequels,
- remakes,
- franchises,
- actors,
- directors,
- writers,
- cinematographers,
- composers,
- editors,
- production designers,
- studios,
- characters,
- books/source material,
- movements,
- countries,
- awards,
- genres,
- themes,
- filming locations,
- influences,
- influenced works when verified.

The graph must be usable as a discovery interface, not only stored in a database.

---

# 30. Collections

Support:
- editorial collections,
- user lists,
- franchise collections,
- award collections,
- director retrospectives,
- actor collections,
- country cinema,
- decade collections,
- genre collections,
- film movements,
- seasonal collections,
- themed collections.

Admin should be able to create and reorder editorial collections without source-code changes.

---

# 31. Film Journeys

Create structured multi-title experiences.

Examples:
- Discover Japanese Cinema
- History of Science Fiction
- Origins of Horror
- Evolution of Animation
- 100 Essential Films
- Great Cinematography
- Film Noir
- French New Wave
- New Hollywood
- Korean Cinema
- History of Anime
- Director Retrospective
- Before You Watch [major sequel/franchise title]

Journey model:
- title,
- description,
- chapters,
- ordered titles,
- optional essays/intros,
- progress,
- completion,
- badges/achievements if appropriate.

---

# 32. After-Credits Room

After a movie/episode is completed, unlock deeper content.

Possible modules:
- user rating,
- written review,
- favorite scene,
- favorite character,
- ending analysis,
- spoiler discussion,
- easter eggs,
- production story,
- behind-the-scenes material,
- deleted-scene metadata/content where licensed,
- commentary,
- critical essays where licensed,
- community reviews,
- recommended next title,
- director/cast exploration.

Spoiler-heavy modules remain locked before completion by default.

---

# 33. Reviews and Community

Potential capabilities:
- star or numeric rating,
- written review,
- spoiler tagging,
- likes/reactions,
- following,
- friends activity,
- lists,
- comments/discussion,
- reporting/moderation controls.

The system must be architected so community features can be enabled gradually.

If community content is enabled, moderation and abuse controls become mandatory before public launch.

---

# 34. Movie Clubs

Support group-oriented film engagement:
- club creation,
- member lists,
- scheduled watch,
- assigned film,
- discussion thread,
- poll,
- club lists,
- watch history.

This may be phase-gated after core streaming.

---

# 35. Watch Parties

Potential later feature:
- synchronized playback,
- private room,
- host controls,
- text reactions/chat,
- join/leave synchronization,
- drift correction.

Rights and regional availability must still be enforced per participant.

---

# 36. Cinema Passport

Every profile receives a long-term personal cinema history.

Track/display:
- films watched,
- episodes watched,
- watch hours,
- first watches,
- rewatches,
- countries explored,
- directors watched,
- actors watched,
- decades,
- genres,
- average rating,
- favorite creators,
- longest/shortest watched title,
- watch streaks only if presented responsibly,
- yearly statistics,
- genre distribution,
- country distribution,
- ratings distribution.

The account should become more valuable over time because it contains the user's film history.

---

# 37. Annual Cinema Report

Create a shareable yearly recap:
- films watched,
- hours,
- top genres,
- top directors,
- top actors,
- favorite-rated films,
- countries,
- decades,
- first watches,
- rewatches,
- milestones.

Respect privacy controls.

---

# 38. Rewatch Intelligence

On a rewatch, optionally surface:
- prior rating,
- previous watch date,
- saved scenes,
- personal notes,
- previous favorite character/scene,
- changes in rating,
- optional spoiler-aware insights because the title was already completed.

Users must be able to turn this off.

---

# 39. Customer Profiles

Multiple customer profiles may exist within one subscriber account even though there is only one platform administrator.

Each profile can maintain independent:
- avatar,
- maturity settings,
- language,
- playback preferences,
- subtitle preferences,
- watch progress,
- watch history,
- My List,
- ratings,
- reviews,
- Taste DNA,
- recommendations,
- Cinema Passport.

Support a child/kids profile architecture if later enabled.

---

# 40. Customer Account Dashboard

Support:
- account profile,
- subscription,
- billing,
- payment methods,
- plan,
- devices/sessions,
- watch history,
- My List,
- downloads if supported,
- profile management,
- playback preferences,
- subtitle preferences,
- notification preferences,
- privacy/preferences,
- security,
- password change,
- sign out,
- sign out other sessions,
- account deletion workflow,
- data-export workflow where legally required.

---

# 41. Subscription Architecture

The platform should be subscription-ready.

Support architecture for:
- plans,
- recurring billing,
- trials if enabled,
- coupons/promotions if enabled,
- failed-payment states,
- grace periods,
- cancellations,
- renewals,
- plan changes,
- entitlement checks,
- simultaneous-stream limits,
- video-quality entitlements,
- download entitlements if implemented.

Do not hardcode payment-provider behavior into domain logic.

---

# 42. Private Admin Studio

Admin route:
`/studio`

Only one administrator is intended.

The Studio must be functional, professional, and built as carefully as the customer site.

---

# 43. Admin Authentication and Security

There must be:
- no public admin signup,
- one provisioned admin account,
- strong password policy,
- MFA support,
- secure session handling,
- rate limiting,
- login audit events,
- session revocation,
- CSRF protection where applicable,
- secure cookies,
- secret management,
- restricted studio routes,
- protection against accidental public exposure.

Admin access must never be controlled only by hiding UI elements.

---

# 44. Admin Dashboard

Show useful operational summaries such as:
- total customers,
- active subscribers,
- views,
- watch hours,
- revenue if billing is integrated,
- currently processing uploads,
- failed jobs,
- recently published titles,
- most watched titles,
- new subscribers,
- storage usage,
- streaming/bandwidth indicators,
- system warnings.

Never display fabricated metrics as if they were real.

---

# 45. Admin Content Library

Support:
- Movies
- Series
- Seasons
- Episodes
- Specials
- Trailers
- Collections
- Journeys

Content status:
- Draft
- Uploading
- Processing
- Ready
- Scheduled
- Published
- Unpublished
- Failed
- Archived

Library controls:
- search,
- filter,
- sort,
- pagination/virtualization,
- bulk actions where safe,
- edit,
- preview,
- publish,
- unpublish,
- schedule,
- archive,
- delete with confirmation.

---

# 46. Movie Creation / Editing

Metadata fields should include as applicable:
- title,
- original title,
- alternate titles,
- short description,
- full synopsis,
- release date,
- year,
- runtime,
- certification,
- countries,
- languages,
- genres,
- themes,
- tags,
- cast,
- characters,
- director,
- writers,
- cinematographer,
- editor,
- composer,
- production designer,
- studio/company,
- franchise,
- source material,
- edition,
- rights window,
- availability territories,
- credits,
- external/authority metadata identifiers if used.

Artwork:
- poster,
- landscape card,
- hero backdrop,
- title logo,
- mobile artwork,
- optional stills.

Media:
- master video,
- trailer,
- teaser,
- clips,
- commentary tracks,
- audio description.

Text/audio:
- subtitles,
- closed captions,
- audio tracks,
- language metadata.

---

# 47. Series Creation / Editing

Workflow:
1. Create Series
2. Create Season
3. Create Episodes
4. Attach assets
5. Process
6. Preview
7. Publish/schedule

Support:
- bulk episode creation,
- bulk upload,
- filename mapping such as `S01E01`,
- reordering,
- specials,
- per-episode metadata,
- per-episode artwork,
- per-episode audio/subtitles,
- season-level artwork,
- series-level metadata inheritance.

---

# 48. Upload Manager

Upload capabilities:
- large-file support,
- resumable/chunked uploads where practical,
- upload progress,
- pause/resume where supported,
- checksum/integrity verification,
- retry,
- cancel,
- duplicate detection warnings,
- file validation,
- file-size/type validation,
- storage quota awareness,
- secure direct-to-object-storage uploads where appropriate.

Never route enormous video files unnecessarily through a single web request handler if a scalable direct-upload pattern is available.

---

# 49. Video Processing Pipeline

Do **not** serve uploaded master files directly to viewers.

Pipeline:

```text
Master Upload
   ↓
Validation
   ↓
Object Storage
   ↓
Metadata Probe
   ↓
Transcode Job
   ↓
Multiple Video Renditions
   ↓
Audio Processing
   ↓
Subtitle/Caption Processing
   ↓
HLS/CMAF Packaging
   ↓
Thumbnail / Sprite Generation
   ↓
Scene / Chapter Processing
   ↓
Quality Validation
   ↓
Ready State
   ↓
CDN / Protected Delivery
```

Support:
- FFmpeg or equivalent media engine,
- adaptive bitrate ladders,
- HLS,
- CMAF where appropriate,
- thumbnails,
- preview sprites,
- chapter markers,
- waveform/data if useful,
- audio normalization policy,
- subtitle conversion/validation,
- job progress,
- retries,
- failed-job diagnosis,
- idempotency.

---

# 50. Scene-Intelligence Processing Pipeline

For titles that support Cinephile features, create a separate enrichment pipeline.

Potential stages:
1. technical metadata extraction,
2. chapter/scene boundary detection,
3. subtitle/transcript ingestion,
4. speaker/character mapping where reliable,
5. entity extraction,
6. cast/character alignment,
7. scene summaries,
8. relationship facts,
9. spoiler-boundary tagging,
10. music metadata alignment,
11. filmmaking metadata alignment,
12. production-note ingestion,
13. embeddings/index creation,
14. knowledge-graph construction,
15. QA/validation,
16. publish scene-intelligence pack.

All generated intelligence must support:
- confidence,
- provenance/source,
- manual admin correction,
- regeneration,
- versioning,
- invalidation when metadata changes.

AI output must not silently become canonical truth.

---

# 51. Admin SceneLens Editor

The administrator should eventually be able to inspect/correct:
- scene boundaries,
- character identity,
- actor mapping,
- scene summaries,
- spoiler cutoff,
- relationships,
- easter eggs,
- production notes,
- soundtrack metadata,
- incorrect AI output.

This is essential for quality control.

---

# 52. Homepage Manager

Admin must control home layout without editing code.

Capabilities:
- choose hero,
- create rail/collection,
- rename rail,
- choose source/query,
- manually pin items,
- reorder items,
- reorder rails,
- schedule rail,
- activate/deactivate rail,
- audience/profile targeting later if needed,
- preview before publishing.

---

# 53. Content Scheduling

Support:
- publish immediately,
- schedule publish,
- schedule unpublish,
- rights-start date,
- rights-end date,
- timezone-aware scheduling,
- status automation.

All server-side scheduling must use consistent timestamp storage and timezone handling.

---

# 54. Admin Analytics

Platform analytics:
- views,
- unique viewers,
- watch hours,
- average watch duration,
- completion,
- drop-off,
- rewatches,
- likes/ratings,
- My List additions,
- search impressions,
- homepage impressions,
- click-through rate,
- conversion to play,
- subscriber metrics,
- plan metrics,
- retention/churn if billing is active.

Per-title analytics:
- retention curve,
- episode funnel,
- quality/buffering metrics,
- playback errors,
- device/browser distribution.

Analytics must distinguish:
- raw events,
- aggregated metrics,
- bots/internal/admin activity where possible.

---

# 55. Search Analytics

Track:
- query,
- result count,
- clicked result,
- no-result searches,
- reformulations,
- conversion to play.

Use these insights to improve:
- metadata,
- aliases,
- recommendations,
- catalog gaps.

---

# 56. Admin User Management

Support:
- customer search,
- account state,
- subscription status,
- profiles,
- sessions/devices,
- account flags,
- access troubleshooting,
- limited safe support actions,
- data export/delete workflows.

Never expose payment secrets or raw credentials.

---

# 57. Core Domain/Data Model

At minimum, architecture should account for:

```text
Admin
AdminSession
AuditLog

User
Profile
ProfilePreference
DeviceSession

Plan
Subscription
PaymentReference
Entitlement

Movie
Series
Season
Episode
Special
Edition

Person
Character
Credit
Company
Franchise

Genre
Theme
Tag
Country
Language

Artwork
VideoAsset
VideoRendition
AudioTrack
SubtitleTrack
CaptionTrack
Trailer
Clip
CommentaryTrack

UploadJob
TranscodeJob
ProcessingJob
SceneIntelligenceJob

Scene
Chapter
SceneEntity
SceneCharacter
SceneRelationship
SceneNote
SceneBookmark
MusicCue
ProductionNote

WatchProgress
WatchEvent
WatchHistory
Rating
Review
Watchlist

Collection
CollectionItem
FilmJourney
JourneyChapter
JourneyItem
JourneyProgress

HomepageRail
HomepageItem

SearchEvent
Recommendation
TasteProfile

Follow
Club
ClubMember
ClubDiscussion
WatchParty

AnalyticsEvent
AggregatedMetric

ContentRights
Territory
AvailabilityWindow
```

Actual tables/models may be normalized differently, but domain coverage must remain.

---

# 58. Recommended Technical Architecture

If the repository is greenfield, prefer a clear service boundary such as:

## Frontend
- TypeScript
- React
- Next.js or equivalent current stable framework
- component system
- responsive design
- accessible primitives
- server/client boundaries chosen intentionally

## Backend
- Python
- FastAPI or equivalent current stable API framework
- typed request/response schemas
- service/repository/domain separation
- OpenAPI documentation

## Primary Database
- PostgreSQL

## Cache / Job Coordination
- Redis

## Background Jobs
- robust Python worker/job system
- retry/backoff
- idempotency
- job status persistence

## Media Storage
Development:
- local S3-compatible object storage such as MinIO

Production:
- S3-compatible managed object storage

## Video Processing
- FFmpeg
- ffprobe
- worker queue

## Streaming
- HLS
- CMAF where appropriate
- CDN in production
- signed/protected media URLs

## Search
Start with PostgreSQL search if adequate, then adopt a dedicated search engine when scale/features justify it.

## AI / Retrieval
- scene-level structured store
- vector/embedding index only where useful
- spoiler-aware retrieval
- provenance-aware generation

## Local Development
- Docker Compose for dependencies
- frontend hot reload
- backend reload
- worker auto-restart where safe

If an existing repository uses a different mature stack, **audit before replacing it**.

---

# 59. API Principles

- version API intentionally,
- typed contracts,
- consistent errors,
- pagination,
- validation,
- authentication/authorization middleware,
- idempotency for sensitive operations,
- rate limits,
- audit sensitive admin mutations,
- no secrets in responses,
- no raw storage paths exposed publicly,
- signed upload/download/streaming flows where appropriate.

---

# 60. Media Security and Delivery

Production design must consider:
- signed URLs/tokens,
- short-lived playback authorization,
- entitlement checks,
- origin protection,
- CDN,
- hotlink protection,
- geo/rights enforcement where required,
- concurrent stream limits,
- DRM architecture if licensed content requires it,
- watermarking architecture if later required.

Do not claim DRM exists until it is implemented and integrated with supported clients.

---

# 61. Rights and Content Compliance

The platform must not assume that possessing a video file grants streaming rights.

Content records should support:
- license/right status,
- territories,
- start/end window,
- editions covered,
- audio/subtitle rights,
- promotional artwork rights,
- trailer/clip rights.

The system must be capable of automatically preventing playback outside configured availability windows.

---

# 62. Security

Mandatory:
- no hardcoded secrets,
- `.env.example`,
- secret separation by environment,
- password hashing using a modern accepted algorithm,
- secure cookies,
- CSRF protection where applicable,
- XSS mitigation,
- output escaping,
- SQL injection prevention via parameterized access/ORM,
- rate limiting,
- secure file validation,
- path traversal protections,
- malware-scanning integration point for uploads if relevant,
- access control enforced server-side,
- audit logs,
- dependency scanning,
- protected admin routes,
- production HTTPS,
- security headers,
- CORS policy,
- session revocation.

---

# 63. Privacy

Support architecture for:
- consent,
- privacy settings,
- watch-history controls,
- personalization controls,
- data export,
- account deletion,
- retention policies,
- analytics privacy,
- separating operational telemetry from unnecessary personal data.

---

# 64. Performance

Customer UX targets should emphasize:
- fast initial shell,
- progressive image loading,
- optimized images,
- lazy loading,
- virtualization where needed,
- prefetch intentionally,
- avoid huge client bundles,
- CDN assets,
- responsive artwork,
- smooth horizontal rails,
- minimal layout shift.

Playback targets:
- rapid start,
- adaptive bitrate,
- low rebuffering,
- robust retry,
- measurable playback QoE.

---

# 65. Responsive Design

Support:
- desktop,
- laptop,
- tablet,
- mobile.

Design each breakpoint intentionally.

Future TV applications must not be blocked by backend design.

---

# 66. Design Language

The product may learn from established streaming interaction patterns but must not clone:
- Netflix branding,
- Netflix logos,
- Crunchyroll branding,
- proprietary copyrighted UI artwork,
- exact visual identity.

Create an original:
- typography system,
- spacing scale,
- motion language,
- card geometry,
- color system,
- icon usage,
- focus states,
- admin design system.

The customer side should feel cinematic.
The admin side should feel precise, data-rich, and operational.

---

# 67. Testing Strategy

## Unit Tests
- domain logic,
- recommendation logic,
- spoiler boundaries,
- entitlements,
- scheduling,
- media metadata,
- helpers.

## Integration Tests
- API + database,
- storage,
- jobs,
- auth,
- publish flows,
- progress sync.

## End-to-End Tests
Critical flows:
- signup/login if enabled,
- profile selection,
- browse,
- search,
- title details,
- play,
- resume,
- My List,
- rating,
- SceneLens,
- admin login,
- upload metadata,
- media processing state,
- preview,
- publish,
- homepage manager.

## Media Tests
- HLS manifest validity,
- rendition outputs,
- audio/subtitle association,
- thumbnail generation,
- failed job recovery.

## Accessibility Tests
- keyboard,
- focus,
- labels,
- contrast,
- player controls.

## Responsive Tests
- target viewport matrix.

---

# 68. Browser Verification

Automated browser testing should use an appropriate framework such as Playwright.

For major visual milestones:
- navigate to live server,
- capture screenshot(s),
- verify no console errors,
- verify no failed API calls,
- verify key interactions,
- store development evidence in an artifacts/test-results location where practical.

---

# 69. Observability

Production-ready design must include:
- structured logs,
- request IDs,
- job IDs,
- media IDs,
- error monitoring,
- health checks,
- readiness checks,
- job queue metrics,
- upload metrics,
- transcoding metrics,
- API latency,
- playback telemetry,
- storage failures,
- alerting hooks.

---

# 70. Project Documentation

Maintain:

```text
README.md
docs/
  ARCHITECTURE.md
  DEVELOPMENT.md
  DEPLOYMENT.md
  SECURITY.md
  MEDIA_PIPELINE.md
  SCENELENS.md
  DATA_MODEL.md
  API.md
  TESTING.md
  PRODUCT_DECISIONS.md
  BUILD_STATUS.md
  CHANGELOG.md
```

Do not allow documentation to drift far behind implementation.

---

# 71. Build Phases

## Phase 0 — Repository Audit and Development Control
- inspect every relevant source/config file,
- identify current architecture,
- identify broken/incomplete work,
- establish status ledger,
- establish live development environment,
- do not destroy working code.

## Phase 1 — Foundation
- frontend shell,
- backend shell,
- database,
- Redis,
- local object storage,
- migrations,
- health endpoints,
- environment management,
- Docker/dev orchestration,
- live customer/studio pages.

## Phase 2 — Authentication and Profiles
- customer auth,
- profile model,
- admin provisioning,
- admin auth/MFA architecture,
- session management.

## Phase 3 — Catalog Domain
- movie/series/season/episode,
- people/credits,
- genres/tags/themes,
- artwork,
- metadata APIs.

## Phase 4 — Customer Catalog UX
- home,
- rails,
- cards,
- movie detail,
- series detail,
- search baseline.

## Phase 5 — Admin Studio CMS
- dashboard,
- content library,
- movie/series editors,
- artwork management,
- publish states.

## Phase 6 — Upload and Media Pipeline
- uploads,
- object storage,
- ffprobe,
- transcode,
- HLS,
- thumbnails,
- processing dashboard.

## Phase 7 — Production Player
- adaptive playback,
- subtitles/audio,
- progress,
- skip markers,
- resume,
- player errors/QoE.

## Phase 8 — Homepage Manager and Scheduling
- editorial rails,
- hero,
- reorder,
- schedule,
- availability windows.

## Phase 9 — Account and Subscription Readiness
- account dashboard,
- plans,
- entitlements,
- billing integration boundary,
- session/device management.

## Phase 10 — Analytics
- event model,
- title analytics,
- retention,
- search analytics,
- admin dashboards.

## Phase 11 — Recommendation Foundation
- user signals,
- explainable baseline recommender,
- recommendation rails,
- cold-start.

## Phase 12 — Movie Prescription and Taste DNA
- intent UI,
- preference model,
- one-perfect-movie,
- recommendation explanation.

## Phase 13 — Cinema Passport
- history,
- stats,
- annual report,
- rewatches.

## Phase 14 — Scene Intelligence Foundation
- scenes,
- transcripts/subtitles,
- entities,
- spoiler boundary,
- scene index,
- admin validation.

## Phase 15 — SceneLens
- pause overlay/panel,
- current characters,
- prior appearances,
- scene explanation,
- filmmaking/music metadata.

## Phase 16 — Ask This Movie
- spoiler-safe retrieval,
- QA layer,
- provenance,
- refusal on unknown facts.

## Phase 17 — Character and Relationship Intelligence
- Who Was That,
- What Did I Miss,
- evolving relationship graph.

## Phase 18 — Cinephile Content
- notes,
- bookmarks,
- film knowledge graph,
- credits explorer,
- collections,
- film journeys,
- edition vault,
- version comparison,
- original presentation metadata,
- after-credits room.

## Phase 19 — Community Expansion
- reviews,
- follows,
- lists,
- clubs,
- optional watch parties,
- moderation.

## Phase 20 — Hardening
- security,
- performance,
- accessibility,
- observability,
- backup/restore,
- load tests,
- failure recovery.

## Phase 21 — Staging
- production-like deployment,
- CDN/object storage,
- migrations,
- protected admin,
- smoke tests,
- end-to-end validation.

## Phase 22 — Production Launch
- release checklist,
- monitoring,
- rollback,
- incident plan,
- final acceptance gates.

---

# 72. Definition of Done

The project is not complete because:
- pages exist,
- mockups look attractive,
- APIs return dummy data,
- uploads accept a file,
- a local MP4 plays,
- or unit tests pass.

The project is complete only when the agreed production scope is:

1. implemented,
2. integrated,
3. database-backed,
4. usable from the running UI,
5. tested,
6. secure,
7. observable,
8. documented,
9. deployable,
10. recoverable,
11. and validated end-to-end.

---

# 73. Mandatory Completion Gates

## Customer Gate
- core browse/search/play/resume flows work,
- responsive UI works,
- accessibility baseline passes,
- no critical console errors.

## Admin Gate
- single admin can securely manage catalog,
- upload/process media,
- preview,
- publish/unpublish,
- manage homepage,
- inspect failures.

## Streaming Gate
- adaptive media is generated,
- manifests work,
- playback authorization works,
- master file is not directly public.

## Data Gate
- migrations reproducible,
- constraints/indexes correct,
- backup/restore tested.

## Intelligence Gate
For enabled AI/Cinephile features:
- spoiler boundary tests pass,
- hallucination/fallback behavior exists,
- provenance/manual correction exists,
- unknown facts are not invented.

## Security Gate
- admin is not publicly registerable,
- secrets are externalized,
- authz enforced server-side,
- vulnerability/dependency checks have no unresolved critical issue.

## Performance Gate
- target pages/player behave acceptably on realistic test devices/connections,
- no obvious unbounded query/render problems.

## Operational Gate
- health checks,
- logs,
- monitoring,
- deployment,
- rollback,
- recovery documented and tested.

---

# 74. Explicit Prohibitions

Codex must NOT:

- downgrade the goal to a bare MVP without explicit instruction;
- rebuild the entire repository before auditing it;
- delete functioning code merely to simplify implementation;
- copy Netflix/Crunchyroll branding;
- create a public admin registration flow;
- hardcode passwords, keys, tokens, or storage credentials;
- expose master video files directly;
- claim DRM, 4K, HDR, AI accuracy, or billing works when it does not;
- fake admin analytics;
- use only mock data for a feature marked complete;
- silently swallow processing errors;
- let AI-generated scene facts become authoritative without provenance/correction;
- reveal spoiler information beyond the allowed timestamp when spoiler protection is enabled;
- move to the next major phase while the current acceptance gate is failing;
- stop maintaining the live development environment after it is established;
- mark UI work done without browser verification;
- leave critical TODOs hidden in source without logging them in `BUILD_STATUS.md`.

---

# 75. Final Product Standard

The finished system should feel like:

- premium streaming,
- deep movie discovery,
- a personal film diary,
- an intelligent scene companion,
- a film knowledge graph,
- a collector/enthusiast archive,
- and a professional content-management studio,

combined into one original platform.

The owner should be able to upload and publish content through one private Admin Studio while customers experience a polished streaming site whose deepest features are specifically designed for people who genuinely love movies.
