import 'package:flutter/material.dart';

class AppTheme {
  static const background = Color(0xFF0B1420);
  static const surface = Color(0xFF142333);
  static const accent = Color(0xFF79E3CE);
  static const muted = Color(0xFFB8C8D8);

  static ThemeData get darkTheme {
    final scheme = ColorScheme.fromSeed(
      seedColor: accent,
      brightness: Brightness.dark,
      primary: accent,
      onPrimary: background,
      surface: surface,
      onSurface: Color(0xFFF2F6FA),
    );
    final shape = RoundedRectangleBorder(
      borderRadius: BorderRadius.circular(16),
    );
    final button = ElevatedButton.styleFrom(
      minimumSize: const Size(48, 56),
      backgroundColor: accent,
      foregroundColor: background,
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
      textStyle: const TextStyle(fontSize: 17, fontWeight: FontWeight.w700),
      shape: shape,
      elevation: 0,
    );
    return ThemeData(
      useMaterial3: true,
      colorScheme: scheme,
      scaffoldBackgroundColor: background,
      visualDensity: VisualDensity.standard,
      appBarTheme: const AppBarTheme(
        backgroundColor: background,
        foregroundColor: Color(0xFFF2F6FA),
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        centerTitle: false,
        titleSpacing: 24,
        toolbarHeight: 72,
        titleTextStyle: TextStyle(fontSize: 22, fontWeight: FontWeight.w700),
      ),
      textTheme: const TextTheme(
        headlineMedium: TextStyle(
          fontSize: 30,
          height: 1.2,
          fontWeight: FontWeight.w700,
          color: Color(0xFFF2F6FA),
        ),
        titleLarge: TextStyle(
          fontSize: 23,
          fontWeight: FontWeight.w700,
          color: Color(0xFFF2F6FA),
        ),
        titleMedium: TextStyle(
          fontSize: 18,
          fontWeight: FontWeight.w600,
          color: Color(0xFFF2F6FA),
        ),
        bodyLarge: TextStyle(
          fontSize: 18,
          height: 1.5,
          color: Color(0xFFF2F6FA),
        ),
        bodyMedium: TextStyle(fontSize: 16, height: 1.5, color: muted),
      ),
      cardTheme: CardThemeData(
        color: surface,
        elevation: 0,
        margin: EdgeInsets.zero,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(20),
          side: const BorderSide(color: Color(0xFF2B4053)),
        ),
      ),
      elevatedButtonTheme: ElevatedButtonThemeData(style: button),
      filledButtonTheme: FilledButtonThemeData(style: button),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          minimumSize: const Size(48, 56),
          foregroundColor: accent,
          shape: shape,
          side: const BorderSide(color: Color(0xFF547486)),
          padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
        ),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: surface,
        contentPadding: const EdgeInsets.symmetric(
          horizontal: 18,
          vertical: 20,
        ),
        border: OutlineInputBorder(borderRadius: BorderRadius.circular(16)),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(16),
          borderSide: const BorderSide(color: Color(0xFF547486)),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(16),
          borderSide: const BorderSide(color: accent, width: 2),
        ),
      ),
      bottomNavigationBarTheme: const BottomNavigationBarThemeData(
        backgroundColor: surface,
        selectedItemColor: accent,
        unselectedItemColor: muted,
        elevation: 0,
        selectedLabelStyle: TextStyle(
          fontWeight: FontWeight.w700,
          fontSize: 12,
        ),
        unselectedLabelStyle: TextStyle(fontSize: 12),
      ),
      dividerTheme: const DividerThemeData(color: Color(0xFF2B4053), space: 32),
    );
  }
}
