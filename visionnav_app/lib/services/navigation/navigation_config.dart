/// Navigation provider configuration.
///
/// Routing uses an OpenRouteService API key.
///   1. Sign in at https://account.heigit.org/ to get a key.
///   2. Enter a token in the app's Settings or pass it at build time:
///        flutter run --dart-define=ORS_API_KEY=your_key_here
///
/// Geocoding (spoken place -> coordinates) uses OpenStreetMap Nominatim and
/// needs no key, but requires a descriptive User-Agent and max 1 request/s.
library;

const String kOrsApiKeyDefault = '';

const String kOrsApiKey = String.fromEnvironment(
  'ORS_API_KEY',
  defaultValue: kOrsApiKeyDefault,
);

/// Runtime override set from Settings for this app session.
String routingApiKey = kOrsApiKey;

/// ISO country code used to bias geocoding results ("pk" = Pakistan).
const String kGeocodeCountryCode = 'pk';

/// Identifies the app to OSM services (Nominatim usage policy requires this).
const String kHttpUserAgent = 'VisionNav-FYP/1.0 (student accessibility project)';
