# FloatyGroove — Roblox R15 dance

An 8-beat looping dance at 120 BPM (4 s): the knees bounce on every beat, the
arms take turns pumping, the hips sway, and the last two beats are a full spin
with arms out. The pose math lives in one module, so the code preview and the
published animation always match.

| File | Where it goes in Studio |
|---|---|
| `FloatyGroove.lua` | ModuleScript in **ReplicatedStorage**, named `FloatyGroove` |
| `DanceController.client.lua` | LocalScript in **StarterPlayer > StarterCharacterScripts** |
| `BuildKeyframes.lua` | Paste into the **Command Bar** (only needed to publish) |

## Quick try (only you see it)

1. Add the module and the LocalScript as shown above.
2. Press Play and hit **G**. Walking, jumping or pressing G again stops the dance.

## Publish it (everyone sees it)

Other players can't see `Motor6D.Transform`, so for multiplayer you need a real animation asset:

1. **Avatar > Rig Builder > R15** (any body type), then select the new rig.
2. Paste `BuildKeyframes.lua` into **View > Command Bar** and press Enter.
   This bakes a `FloatyGroove` KeyframeSequence into `Rig.AnimSaves`.
3. Publish it in either of these ways:
   - Open the **Animation Editor** on the rig, load `FloatyGroove` and choose **Publish to Roblox**.
   - Right-click the KeyframeSequence in the Explorer and choose **Save to Roblox**.
4. Copy the asset ID into `ANIMATION_ID` in `DanceController.client.lua`.

Tweak `BPM`, the amplitudes in `pose()`, or `TOGGLE_KEY` to taste. If you edit
the module, re-run the bake step in a fresh Studio session, since the Command
Bar caches `require`.
