# Promo video source

`promo.html` is the animation (one `render(t)` function draws the frame at time `t`), `render.js` captures its 480 frames
with Playwright, and `music.py` generates the original soundtrack. To rebuild `../sanad-promo.mp4`:

```bash
node render.js
python music.py
ffmpeg -framerate 30 -i frames/f%04d.jpg -i music.wav -c:v libx264 -crf 22 -pix_fmt yuv420p -c:a aac -b:a 160k -shortest -movflags +faststart ../sanad-promo.mp4
```

Run them from this folder.
