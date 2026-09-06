"""Independent cursor press feedback, driven by editable source-time clicks."""
import math


def press_scale(events,t):
    """A brief compression keeps the pointer tip fixed while signaling a click.

    Existing recordings contain click instants, not button-hold intervals.
    Overlapping clicks share a bounded pulse without compounding shrinkage.
    """
    amounts=[math.sin(math.pi*(t-event['t'])/.24)
             for event in events if event.get('kind')=='click' and not event.get('hidden')
             and 0<=event.get('x',.5)<=1 and 0<=event.get('y',.5)<=1 and 0<=t-event['t']<.24]
    return 1-.18*max(amounts,default=0)
