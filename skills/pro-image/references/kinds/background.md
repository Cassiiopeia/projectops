# Kind: background

A full-frame scene behind UI or characters (game scenes, onboarding, hero sections, login screens).

## Brief must have
- Exact final size from the slot (full screen of a 16:9 game = 1920x1080; a 3:2 hero = 1536x1024).
- Which zones UI covers (dialogue box, header, buttons) and must stay calm and empty.
- Time of day, weather, mood. Whether characters appear (usually: none; characters are separate sprites).

## Prompt pattern
```
Background art for <app/screen>, shown full screen behind <UI>.
Scene: <place>, <time of day>, <weather>. Main elements, most important first: <A>, <B>, <C>.
Camera: <eye-level / low angle / wide>, focal point <left third / center>.
Keep the <bottom third / top 15%> quiet and free of important objects: <UI> covers it.
Style: <STYLE.md look in 2-4 lines>. Light: <direction and color>. Palette: <colors>.
No people, no text, no signs with letters, no logos, no frame.
```

## Traps
- Signs, menus and posters grow random letters. Say "no readable text anywhere" and "blank signs".
- People appear in public places. Say "empty, no people" twice when the scene is a cafe or street.
- Opaque only. Never ask for transparency.
- Run without `--alpha`. Size mismatch is fixed with `cover` (crop), so leave margin around the focal point.
