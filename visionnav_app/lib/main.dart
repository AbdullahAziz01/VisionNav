import 'package:flutter/material.dart';
import 'package:visionnav_app/core/theme.dart';
import 'package:visionnav_app/screens/home_screen.dart';
import 'package:visionnav_app/screens/camera_screen.dart';
import 'package:visionnav_app/screens/navigation_screen.dart';
import 'package:visionnav_app/screens/settings_screen.dart';
import 'package:visionnav_app/screens/help_screen.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const VisionNavApp());
}

class VisionNavApp extends StatelessWidget {
  const VisionNavApp({Key? key}) : super(key: key);

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'VisionNav',
      theme: AppTheme.darkTheme,
      home: const MainLayout(),
      debugShowCheckedModeBanner: false,
    );
  }
}

class MainLayout extends StatefulWidget {
  const MainLayout({Key? key}) : super(key: key);

  @override
  State<MainLayout> createState() => _MainLayoutState();
}

class _MainLayoutState extends State<MainLayout> {
  int _currentIndex = 0;

  Widget _screenForIndex(int index) {
    switch (index) {
      case 0:
        return const HomeScreen();
      case 1:
        return const CameraScreen();
      case 2:
        return const NavigationScreen();
      case 3:
        return const SettingsScreen();
      case 4:
        return const HelpScreen();
      default:
        return const HomeScreen();
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: _screenForIndex(_currentIndex),
      bottomNavigationBar: BottomNavigationBar(
        currentIndex: _currentIndex,
        onTap: (index) {
          setState(() {
            _currentIndex = index;
          });
        },
        type: BottomNavigationBarType.fixed,
        items: const [
          BottomNavigationBarItem(icon: Icon(Icons.home), label: 'Home'),
          BottomNavigationBarItem(icon: Icon(Icons.camera_alt), label: 'Vision'),
          BottomNavigationBarItem(icon: Icon(Icons.navigation), label: 'Nav'),
          BottomNavigationBarItem(icon: Icon(Icons.settings), label: 'Settings'),
          BottomNavigationBarItem(icon: Icon(Icons.help), label: 'Help'),
        ],
      ),
    );
  }
}
