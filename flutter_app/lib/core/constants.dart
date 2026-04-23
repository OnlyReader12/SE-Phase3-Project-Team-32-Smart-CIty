const String kBaseUrl = 'http://127.0.0.1:8003';

// Route names
const String kRouteLogin       = '/login';
const String kRouteRegister    = '/register';
const String kRouteDashboard   = '/dashboard';

// Storage keys
const String kTokenAccess  = 'access_token';
const String kTokenRefresh = 'refresh_token';
const String kUserRole     = 'user_role';
const String kUserTeam     = 'user_team';
const String kUserId       = 'user_id';

// Roles
const String kRoleResident  = 'RESIDENT';
const String kRoleSmartUser = 'SMART_USER';
const String kRoleAnalyst   = 'ANALYST';
const String kRoleServicer  = 'SERVICER';
const String kRoleManager   = 'MANAGER';

// Domains
const List<String> kDomains = ['energy', 'water', 'air'];

// Campus zones (mirrors node_schemas.json)
const List<Map<String, String>> kCampusZones = [
  {'id': 'BLK-A',     'name': 'Engineering Block A'},
  {'id': 'BLK-B',     'name': 'Engineering Block B'},
  {'id': 'LIB',       'name': 'Central Library'},
  {'id': 'HOSTEL-N',  'name': 'North Hostel'},
  {'id': 'HOSTEL-S',  'name': 'South Hostel'},
  {'id': 'CAFETERIA', 'name': 'Main Cafeteria'},
  {'id': 'SPORTS',    'name': 'Sports Complex'},
  {'id': 'ADMIN',     'name': 'Administration Block'},
  {'id': 'GARDEN',    'name': 'Campus Garden'},
  {'id': 'PARKING',   'name': 'Parking Lot'},
];
