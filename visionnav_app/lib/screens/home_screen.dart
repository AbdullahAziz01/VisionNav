import 'package:flutter/material.dart';

class HomeScreen extends StatelessWidget {
  const HomeScreen({Key? key}) : super(key: key);

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('VisionNav Home')),
      body: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: const [
            Icon(Icons.accessibility_new, size: 80, color: Colors.tealAccent),
            SizedBox(height: 20),
            Text(
              'Welcome to VisionNav',
              style: TextStyle(fontSize: 24, fontWeight: FontWeight.bold),
            ),
            SizedBox(height: 10),
            Text('Select a mode from the navigation bar below.'),
          ],
        ),
      ),
    );
  }
}
