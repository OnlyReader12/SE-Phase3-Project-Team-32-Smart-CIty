import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../core/api_client.dart';
import '../core/constants.dart';

// ── Auth State ─────────────────────────────────────────────────────────────

class AuthState {
  final bool isLoggedIn;
  final String? role;
  final String? team;      // 'ENERGY' | 'EHS' | 'RESIDENTS'
  final String? userId;
  final bool isLoading;
  final String? error;

  const AuthState({
    this.isLoggedIn = false,
    this.role,
    this.team,
    this.userId,
    this.isLoading = false,
    this.error,
  });

  AuthState copyWith({
    bool? isLoggedIn, String? role, String? team, String? userId,
    bool? isLoading, String? error,
  }) => AuthState(
    isLoggedIn: isLoggedIn ?? this.isLoggedIn,
    role:       role       ?? this.role,
    team:       team       ?? this.team,
    userId:     userId     ?? this.userId,
    isLoading:  isLoading  ?? this.isLoading,
    error: error,
  );
}

// ── Auth Notifier ──────────────────────────────────────────────────────────

class AuthNotifier extends StateNotifier<AuthState> {
  AuthNotifier() : super(const AuthState()) {
    _loadFromStorage();
  }

  Future<void> _loadFromStorage() async {
    final prefs = await SharedPreferences.getInstance();
    final token = prefs.getString(kTokenAccess);
    final role  = prefs.getString(kUserRole);
    final team  = prefs.getString(kUserTeam);   // restore team
    final uid   = prefs.getString(kUserId);
    if (token != null && role != null) {
      state = state.copyWith(isLoggedIn: true, role: role, team: team, userId: uid);
    }
  }

  Future<bool> login(String email, String password) async {
    state = state.copyWith(isLoading: true, error: null);
    try {
      final resp = await ApiClient.instance.post('/auth/login',
          data: {'email': email, 'password': password});
      await _saveTokens(resp.data);
      return true;
    } catch (e) {
      state = state.copyWith(isLoading: false, error: _parseError(e));
      return false;
    }
  }

  Future<bool> register(String email, String password, String fullName, String? phone) async {
    state = state.copyWith(isLoading: true, error: null);
    try {
      final resp = await ApiClient.instance.post('/auth/register', data: {
        'email': email, 'password': password,
        'full_name': fullName, 'phone_number': phone,
      });
      await _saveTokens(resp.data);
      return true;
    } catch (e) {
      state = state.copyWith(isLoading: false, error: _parseError(e));
      return false;
    }
  }

  Future<void> logout() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.clear();
    state = const AuthState();
  }

  Future<void> _saveTokens(Map data) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(kTokenAccess,  data['access_token']);
    await prefs.setString(kTokenRefresh, data['refresh_token']);
    await prefs.setString(kUserRole,     data['role']);
    await prefs.setString(kUserTeam,     data['team'] ?? 'RESIDENTS'); // save team

    // Fetch user profile to get user_id
    try {
      final me = await ApiClient.instance.get('/auth/me');
      await prefs.setString(kUserId, me.data['id']);
      state = state.copyWith(
        isLoggedIn: true, isLoading: false,
        role: data['role'], team: data['team'] ?? 'RESIDENTS',
        userId: me.data['id'],
      );
    } catch (_) {
      state = state.copyWith(
        isLoggedIn: true, isLoading: false,
        role: data['role'], team: data['team'] ?? 'RESIDENTS',
      );
    }
  }

  String _parseError(dynamic e) {
    try {
      return e.response?.data['detail'] ?? 'An error occurred';
    } catch (_) {
      return 'Network error — check your connection';
    }
  }
}

final authProvider = StateNotifierProvider<AuthNotifier, AuthState>(
  (_) => AuthNotifier(),
);
