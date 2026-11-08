# VisionNav voice and touch controls

The app opens on Live Vision. Its foreground command listener starts after microphone permission is granted. Existing touch controls remain available.

## Commands

| Screen | Say |
|---|---|
| Any main screen | Open home; open camera; add location; open GPS; open settings; open help; plan a bus trip; go back; voice help; stop listening |
| Live Vision | Mute announcements; unmute announcements; repeat detection; camera status; retry camera; open permission settings; end bus trip |
| Navigation | Add location; change destination; start navigation; stop navigation; repeat instruction; my location; scan bus |
| Destination planner | Say a destination, such as Karachi Company. Say check wait to refresh the scheduled estimate. Say walk to mapped stop to start the pilot walk. Answer yes or no if walking is offered. |
| Manual bus planner | List routes; next routes; previous routes; select route [name or displayed page number]; list directions; select direction [name or number]; continue; cancel |
| Settings | Edit backend URL; edit API key; edit routing key; confirm; cancel; save settings; test connection; development mode; production mode; show API key; hide API key; new session; force takeover |
| Help | Read help |
| Current screen | Screen commands |

In the manual bus planner, route numbers are 1-5 within the current spoken page. Route selection reads the available directions. Say continue only after selecting the route and direction. Routes come from the existing bundled records.

Settings dictation receives the next phrase as the exact field value, then requires confirm before applying it to the field. Say save settings to apply the form. Keys are not spoken back or shown in the command status. Arbitrary mixed-case keys and URLs can be misrecognized; touch/paste remains available. Force takeover requires a separate spoken confirm.

The direct-trip planner uses [CDA timetables](https://www.cda.gov.pk/cdaTransitMap) and mapped OpenStreetMap stops. The asset audits all 22 listed routes and supports 15 routes across 49 mapped stops. Some stops are missing on supported routes. The app uses Islamabad time. These PDFs list scheduled trips without a service-day calendar or live updates. When available, the planner adds the pedestrian route estimate to the mapped stop and a two-minute boarding allowance. At the stop, say check wait to refresh. The exact boarding point still needs field verification.

While walking to a mapped stop, the camera shows the GPS instruction. Turn guidance can interrupt camera speech. Walking camera alerts use nearby detections and discard frames older than three seconds. At arrival, use check wait in the scanner. The FR-07 G-11 sign is used only for supported exits before G-11. Confirm the boarding point and your exit with the driver. Imported routes without a verified OCR direction also require driver confirmation.

## Microphone behavior

- Commands use English recognition (en_US), as the existing destination input did.
- Listen while the status says Listening for a command. Recognition pauses for app speech, during destination entry, and when the app is in the background.
- Android recognition uses short sessions, rearmed while the app is foregrounded. This is not an always-on background wake-word engine. Device recognizer/network behavior and short gaps require phone testing.
- Say stop listening to pause. Use the Resume voice button to restart; the bus planner also has a Resume voice commands microphone button. A stopped microphone cannot hear a resume command.
- During destination entry, explicit app navigation commands such as go back are handled as commands instead of being submitted as place names.
- The OS may require touches to grant initial permissions. Do not run another listening assistant continuously alongside the app's recognizer.

## Launching while the app is closed

Configure Android's assistant or Voice Access on the phone. Its open-app command must match the installed label (VisionNav, or VisionNav Demo for the older separate demo build). This repository does not install or configure the phone's system assistant.

Official references:
- https://support.google.com/accessibility/android/answer/6151848
- https://support.google.com/accessibility/android/answer/6151854
- https://pub.dev/packages/speech_to_text/versions/7.4.0

## Physical-phone acceptance checks (pending)

1. Install the updated APK. Allow camera and microphone sequentially. Confirm Live Vision opens and speaks its introduction.
2. Say add location. Hear Where would you like to go? Say a real destination and verify it is used by the existing GPS/routing flow.
3. During another destination prompt say go back. Verify that phrase is not geocoded.
4. Switch among camera, Home, Settings, and Help using voice and touch.
5. Say plan a bus trip, then Karachi Company. Check that the proposed FR-07 direction and stop order match your location. Repeat with touch entry. For the manual planner, test list routes, select route, select direction, and continue.
6. Test connection and save settings by voice. Check invalid URL feedback and cancellation of dictated values.
7. Pause/resume commands; deny microphone permission and recover from Android Settings; test with recognizer network unavailable.
8. Background/foreground the app. Verify there is no background listening and only one listener resumes.
9. Test commands between object announcements in a quiet room and outdoors. Confirm detection, distances, bus OCR, and navigation announcements remain functional.
10. Verify launching through the phone's configured system assistant separately.
