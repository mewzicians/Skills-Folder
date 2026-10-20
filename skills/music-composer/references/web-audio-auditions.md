# Web Audio Auditions

Read this before building, repairing, or verifying an audition or cue that
plays through the Web Audio API, or other code-generated music. These are
cautions observed in practice, not guarantees for every browser. Any timing
or level figure you record is an example measured on one browser and version,
not a constant; measure your own page.

## Keep One Stable Graph

Build the audio graph once per page load and keep it: route sources into
long-lived gain, bus, and processing nodes rather than rebuilding the chain
for each play, stop, or seek. Start, stop, and disconnect sources cleanly, and
release finished ones so long sessions do not accumulate nodes or scheduled
events.

## Settle Dynamics Before The First Note

A compressor or limiter can start in heavy gain reduction, or ramp its
reduction during the first moments after the graph starts, so the first
notes may play quieter or pump audibly. Give such a page a short silent
pre-roll before the first scheduled note, and measure its length on that page
rather than copying a value from another one.

## Test The First Play After A Reload

A defect can appear only on the first play after a page reload, when the
audio context, graph, and processors are new, and vanish after a stop and
replay. Test the first play after a fresh reload as its own case, not only
the first play after a stop.

## Verification Checklist

Verify complete phrases, several uninterrupted loops, stop and replay, pause
and resume, seeking, rapid switching between candidates, long-playback
stability, source cleanup, clipping, static, clicks, dropouts, and usable
loudness at realistic settings. Technical success does not approve the
composition.

Measure scheduler lateness and other timing-sensitive behavior one run at a
time, with no other heavy work on the machine, because CPU contention can
manufacture the lateness being measured. Repeat long playback runs only when a
change could affect loops, the scheduler, wraparound, or source cleanup; say
which checks ran shortened.

## Older Pages

When an existing audition lacks a check or safeguard described here, report
it rather than retrofitting it. Change that page only when the user asks,
because editing a compared page rewrites the evidence a past verdict relied
on; a repaired copy can be built as a new page instead.
