/// Navigation provider configuration.
///
/// Routing uses OpenRouteService (free key, 2,000 requests/day):
///   1. Sign up at https://openrouteservice.org/dev/#/signup
///   2. Create a token, paste it into [kOrsApiKeyDefault] below
///      OR pass it at build time:
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

/// ISO country code used to bias geocoding results ("pk" = Pakistan).
const String kGeocodeCountryCode = 'pk';

/// Identifies the app to OSM services (Nominatim usage policy requires this).
const String kHttpUserAgent = 'VisionNav-FYP/1.0 (student accessibility project)';
