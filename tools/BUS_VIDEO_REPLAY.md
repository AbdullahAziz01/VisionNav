# Testing recorded bus videos

`replay_bus_video.py` sends sampled frames through the running VisionNav
`POST /pipeline/frame` endpoint. It uses a single session ID and sends frames
one at a time, allowing the backend's existing detector, tracker and route OCR
logic to process a sequence. It does not change the mobile app's live scanner.

## Add your recordings

Copy each original recording into `test_videos/bus_routes/` in the project.
That folder is intentionally ignored by Git, so large or identifiable videos
will not be included in a commit. Keep the original video files unchanged.

## Run a replay

1. Start the VisionNav backend the same way you normally do (Docker is fine).
2. Open PowerShell in the project folder and activate the same Python
   environment used by the backend.
3. Run one video, replacing the example filename:

   ```powershell
   python tools/replay_bus_video.py "test_videos/bus_routes/my_bus_video.mp4" --api http://127.0.0.1:8000
   ```

   If the backend requires its API key, set it for this PowerShell window
   before running the command:

   ```powershell
   $env:VISIONNAV_API_KEY = "your-backend-api-key"
   ```

4. The tool reports each uploaded frame and saves a CSV summary plus complete
   JSON responses under `runs/bus_video_tests/`. Those result files are also
   ignored by Git.

By default, every sixth frame is sampled and uploads are limited to two frames
per second. This is intended for manageable offline evaluation; it is not a
real-time performance measurement. Use `--sample-every 1` to inspect every
frame, or adjust `--max-fps` if the backend can handle a different rate.

For useful route-reading examples, record several buses with the destination
display visible, including near and far views, different angles, motion blur,
and clips where no route text is readable. Note the correct route and direction
for each clip separately so the output can be compared against ground truth.

The results show what the running backend returned. They do not by themselves
establish route-recognition accuracy; each clip must be checked against its
known correct route and direction.
