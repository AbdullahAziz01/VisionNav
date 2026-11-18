# VisionNav for Android

VisionNav gives spoken walking directions to a bus stand and helps identify a selected bus from its route sign.

## Set up the phone

1. Start the Python backend using the [project README](../README.md). For a phone on the same trusted Wi-Fi network, bind it to the computer's network interface with `python -m uvicorn main:app --host 0.0.0.0 --port 8000 --workers 1`. For a remote deployment, follow the [HTTPS deployment guide](../docs/deployment_guide.md).
2. Build the APK from this directory with `flutter build apk --debug` and install it on the phone. Allow location, microphone, and camera access when prompted.
3. In the app's Settings, enter the OpenRouteService key and the backend address. For a local test, use the computer's Wi-Fi IP address, for example `http://192.168.1.100:8000`. For an HTTPS deployment, select Production and enter the backend key. Use **Test Connection**.
4. Settings entered on the phone apply until the app process restarts. A demo build can supply defaults with `--dart-define=ORS_API_KEY=...` and `--dart-define=VISIONNAV_API_URL=...`.

If Android reports that an existing VisionNav app has a different signing key, set `VISIONNAV_DEMO_BUILD=true` before the debug build. The APK will install separately as **VisionNav Demo**.

## Demo the trip

1. From **Home**, choose **Plan a bus trip** and select a known route and the destination displayed on its sign. For example, select **Green Line** toward **Barakahu**.
2. Say the name of the bus stand or use **Type bus stand name**. Follow the spoken walking instructions. The **Repeat instruction** button reads the upcoming instruction again.
3. When walking guidance reaches the stand, the app opens **Bus Scanner**. If the app was in the background, return to Navigation and choose **Scan for your bus**. Point the rear camera at the bus sign.
4. Try a sign for the selected route and direction, then a different route or the reverse direction. The app says when a stable reading matches the selection. The user should confirm the destination with the driver before boarding.

The trip picker matches a route and direction the user already knows. The route database has limited stop coverage and provides no live service status.

Run the app tests with `flutter test`. After editing the backend route catalog, regenerate the bundled picker data from the repository root with `python tools/build_bus_trip_options.py`.

## Check distance and OCR before the viva

* With the demo phone streaming, record estimates for a stationary person at tape-measured distances of 1, 2, 3, and 5 metres. Take multiple readings at each distance and repeat in outdoor light. Compare the estimates with the measured distances. If fitting a new calibration, use a separate set of recordings to check the result.
* Test a readable sign with the expected route and direction, the same route in the reverse direction, a different route, and a route code with an unreadable direction. Only the first case should confirm the selected bus.
* For the final rehearsal, use the remote HTTPS address in Settings and repeat the demo over mobile data with USB disconnected and the laptop off.
