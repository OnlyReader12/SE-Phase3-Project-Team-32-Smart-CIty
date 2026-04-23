import 'package:go_router/go_router.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter/material.dart';
import '../providers/auth_provider.dart';
import '../core/constants.dart';
import '../screens/auth/login_screen.dart';
import '../screens/auth/register_screen.dart';
import '../screens/dashboard/resident_dashboard.dart';
import '../screens/dashboard/analyst_dashboard.dart';
import '../screens/dashboard/servicer_dashboard.dart';
import '../screens/dashboard/manager_dashboard.dart';

final routerProvider = Provider<GoRouter>((ref) {
  final auth = ref.watch(authProvider);

  return GoRouter(
    initialLocation: kRouteDashboard,
    redirect: (context, state) {
      final loggedIn = auth.isLoggedIn;
      final onAuth   = state.matchedLocation == kRouteLogin ||
                       state.matchedLocation == kRouteRegister;
      if (!loggedIn && !onAuth) return kRouteLogin;
      if (loggedIn && onAuth)  return kRouteDashboard;
      return null;
    },
    routes: [
      GoRoute(path: kRouteLogin,    builder: (_, __) => const LoginScreen()),
      GoRoute(path: kRouteRegister, builder: (_, __) => const RegisterScreen()),
      GoRoute(
        path: kRouteDashboard,
        builder: (_, __) {
          // BUG FIX: SMART_USER was falling through to LoginScreen
          return switch (auth.role) {
            kRoleResident  => const ResidentDashboard(),
            kRoleSmartUser => const ResidentDashboard(), // Smart User = Resident with toggle
            kRoleAnalyst   => const AnalystDashboard(),
            kRoleServicer  => const ServicerDashboard(),
            kRoleManager   => const ManagerDashboard(),
            _              => const LoginScreen(),
          };
        },
      ),
    ],
  );
});
