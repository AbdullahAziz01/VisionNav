"""

VisionNav - Live camera + full pipeline (YOLO + ByteTrack + depth + distance)

Usage: python camera_detect.py

Press Q to quit.

"""

import sys

import time



import cv2



from pipeline import PipelineConfig, VisionNavPipeline



WINDOW = "VisionNav Pipeline"





def draw_hud(frame, fps: float, result):

    cv2.putText(

        frame,

        f"FPS: {fps:.1f} | Mode: {result.mode} | Tracks: {len(result.objects)}",

        (10, 30),

        cv2.FONT_HERSHEY_SIMPLEX,

        0.7,

        (0, 255, 0),

        2,

    )

    y = 60

    for obj in result.objects[:5]:

        text = f"ID {obj.track_id} {obj.class_name}: {obj.distance_label}"

        cv2.putText(frame, text, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)

        y += 22

    cv2.putText(

        frame,

        "Press Q to quit",

        (10, frame.shape[0] - 20),

        cv2.FONT_HERSHEY_SIMPLEX,

        0.7,

        (255, 255, 255),

        2,

    )





def main():

    pipeline = VisionNavPipeline(PipelineConfig())

    from pipeline.camera import open_camera



    cap = open_camera(pipeline.config.camera_index)

    if not cap.isOpened():

        print("ERROR: Could not open webcam.")

        sys.exit(1)



    print(f"Pipeline mode: {pipeline.active_mode}")

    print(f"Tracker: {pipeline.tracker.name}")

    print("Starting live pipeline. Press Q to quit.")



    prev_time = time.time()

    try:

        while True:

            ret, frame = cap.read()

            if not ret:

                break



            stereo_pair = pipeline._read_stereo_frames() if pipeline.stereo_status.available else None

            result = pipeline.process_frame(frame, stereo_pair=stereo_pair)



            display = frame.copy()

            for obj in result.objects:

                x1, y1, x2, y2 = map(int, obj.bbox_xyxy)

                cv2.rectangle(display, (x1, y1), (x2, y2), (0, 255, 0), 2)



            now = time.time()

            fps = 1.0 / max(now - prev_time, 1e-6)

            prev_time = now

            draw_hud(display, fps, result)



            cv2.imshow(WINDOW, display)

            if cv2.waitKey(1) & 0xFF in (ord("q"), ord("Q")):

                break

    finally:

        cap.release()

        pipeline.release()

        cv2.destroyAllWindows()





if __name__ == "__main__":

    main()

