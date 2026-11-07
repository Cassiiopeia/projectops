# Motion and linked prototypes

> When to read: the mockup moves, or an action on one screen changes another.

Everything here runs in the browser with plain JavaScript. There are no libraries and no build step. `viewer.js` is already loaded and gives you `UIDesign`. A full document (`<!DOCTYPE html>`) gets `viewer.js` too, but link `/assets/viewer.css` yourself if you want its classes.

## Comparing motion options

Register each option. The toolbar's Play all, speed and Start over then work without more code.

```html
<div class="ui-options" id="options"></div>
<script>
  // Each card: .ui-option with an h3 (its name goes into the click record), a [data-play] and a [data-choice] button
  UIDesign.registerOption("a", {
    play: () => UIDesign.animate(sheet, [{ transform: "translateY(100%)" }, { transform: "none" }],
      { duration: 320, easing: "cubic-bezier(.2,.8,.2,1)", fill: "forwards" }),
    reset: () => { sheet.style.transform = "translateY(100%)"; },
  });
</script>
```

| Tool | Use |
|---|---|
| `UIDesign.animate(element, keyframes, timing)` | Web Animations. The speed setting scales `duration` and `delay`. Start over cancels it |
| `UIDesign.spring(onFrame, { dampingRatio, frequency })` | Calls `onFrame(position)` every frame, position 0 to 1. Below `dampingRatio: 1` it overshoots |
| `UIDesign.play(id)` · `playAll()` · `reset()` | Same as the buttons |
| `UIDesign.getSpeed()` | Multiply your own timers by this, or slow motion will not apply to them |

Always pass `reset`, and return the element to its starting look in it. Replay and Start over depend on it.

## Linked prototypes

Several screens share one state. An action on one screen updates the others. Roles and the number of screens come from the project: guardian and child, seller and buyer, admin and user.

```html
<div id="stage"></div>
<script>
  const store = UIDesign.createStore({ sent: [] });
  const steps = UIDesign.showSteps(["Press Send", "Check the other screen"], { title: "Try this" });
  UIDesign.setScreens([
    { id: "sender", label: "Sender", render(element, state) {
      element.innerHTML = `<button id="send">Send</button>`;
      element.querySelector("#send").onclick = () => {
        store.set((current) => ({ sent: [...current.sent, "Routine"] }));
        UIDesign.toast("Sent");
        steps.complete(0);
      };
    } },
    { id: "receiver", label: "Receiver", device: "tablet", render(element, state) {
      element.textContent = state.sent.join(", ") || "Nothing yet";
    } },
  ], store, document.getElementById("stage"));
</script>
```

| Tool | Use |
|---|---|
| `createStore(initial)` | `get` · `set(patch or function)` · `subscribe` · `reset`. Start over restores `initial` |
| `setScreens(screens, store, container)` | One device frame per screen. `render` runs again on every change, so wire events inside it. `device` pins a frame; otherwise the toolbar decides |
| `showSteps(steps, { title })` | A checklist beside the screens. `complete(index)` strikes a step |
| `onLongPress(element, callback, { milliseconds })` | Long press. The click after it is swallowed |
| `onDrag(element, { start, move, end })` | Each gets `{ x, y, dx, dy, distance, event }`. Set `touch-action: none` on the element |
| `toast(text)` · `onReset(callback)` | Short message · extra cleanup on Start over |

Build real interaction, not a slide show: errors, empty states, undo, and the same action twice. Give it the steps panel so a person knows what to try.

**State this to the user:** a linked prototype is fake behavior. It settles flow and screens. It proves nothing about the real server, push or login, so it is never evidence in `facts`.

## From a framework's motion to CSS

Read the project's real values first (`tokens` finds motion files). Then translate them.

| Framework value | In the mockup |
|---|---|
| Flutter `Curves.ease` · iOS default ease | `cubic-bezier(.25,.1,.25,1)` |
| Flutter `easeIn` · `easeOut` · `easeInOut` | `cubic-bezier(.42,0,1,1)` · `(0,0,.58,1)` · `(.42,0,.58,1)` |
| Flutter `fastOutSlowIn` · Compose `FastOutSlowInEasing` | `cubic-bezier(.4,0,.2,1)` |
| Compose `LinearOutSlowInEasing` · `FastOutLinearInEasing` | `cubic-bezier(0,0,.2,1)` · `(.4,0,1,1)` |
| Flutter `easeOutCubic` · `easeInOutCubic` | `cubic-bezier(.215,.61,.355,1)` · `(.645,.045,.355,1)` |
| Flutter `easeOutBack` | `cubic-bezier(.175,.885,.32,1.275)` |
| Flutter `SpringDescription(mass, stiffness, damping)` | `frequency = sqrt(stiffness / mass)`, `dampingRatio = damping / (2 * sqrt(stiffness * mass))` |
| SwiftUI `.spring(response, dampingFraction)` | `frequency = 2π / response`, `dampingRatio = dampingFraction` |
| Compose `spring(dampingRatio, stiffness)` | `frequency = sqrt(stiffness)`, same `dampingRatio` |
| `elasticOut`, `bounceOut` and other non-cubic curves | Compute them in JavaScript with `requestAnimationFrame` |

**State this to the user:** native motion in a browser is an approximation. Check the final feel on a real device (`pro-launch app record`), and show that recording in a card to compare.
