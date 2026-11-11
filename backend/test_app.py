import os,tempfile,unittest
from datetime import datetime,timedelta,timezone
from zoneinfo import ZoneInfo
_temp=tempfile.TemporaryDirectory()
os.environ['DATABASE_PATH']=_temp.name+'/test.db'
os.environ['ADMIN_INITIAL_PASSWORD']='test-only-strong-password'
from app import app,db,ADMIN
class FrontDeskTest(unittest.TestCase):
 def setUp(self):
  self.c=app.test_client()
  from app import limiter
  limiter.reset()
  with app.app_context():
   db().execute('DELETE FROM visits');db().execute('DELETE FROM sessions');db().execute("DELETE FROM users WHERE email!='cculturausallc@gmail.com'");db().commit()
  r=self.c.post('/api/login',json={'email':ADMIN,'password':'test-only-strong-password'})
  self.h={'Authorization':'Bearer '+r.json['token']}
 def test_checkin_privacy_and_validation(self):
  self.assertEqual(self.c.get('/api/visits').status_code,401)
  self.assertEqual(self.c.post('/api/visits',json={}).status_code,400)
  self.assertEqual(self.c.post('/api/visits',json={'first_name':'Test','last_name':'Visitor','email':'test@example.com','phone':'9545550100','zip_code':'33301','visit_reason':'Badge Pickup'}).status_code,201)
 def test_week_history_pagination_and_status(self):
  monday=datetime.now(ZoneInfo('America/New_York')).replace(hour=10,minute=0,second=0,microsecond=0)
  monday-=timedelta(days=monday.weekday())
  with app.app_context():
   for i in range(52):
    stamp=(monday+timedelta(minutes=i)).astimezone(timezone.utc).isoformat()
    db().execute('INSERT INTO visits(first_name,last_name,email,phone,zip_code,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',('Week','Visitor',f'test{i}@example.com','9545550100','33301',stamp,stamp))
   for name,stamp in [('Weekend',monday+timedelta(days=5)),('Historical',monday-timedelta(days=7))]:
    stamp=stamp.astimezone(timezone.utc).isoformat()
    db().execute('INSERT INTO visits(first_name,last_name,email,phone,zip_code,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',(name,'Visitor','past@example.com','9545550100','33301',stamp,stamp))
   db().commit()
  r=self.c.get('/api/visits',headers=self.h).json
  self.assertEqual(r['total'],52);self.assertEqual(len(r['items']),50)
  self.assertLess(r['items'][0]['created_at'],r['items'][1]['created_at'])
  self.assertEqual(len(self.c.get('/api/visits?page=2',headers=self.h).json['items']),2)
  v=r['items'][0]['id']
  self.assertEqual(self.c.patch(f'/api/visits/{v}',headers=self.h,json={'status':'completed'}).status_code,200)
  self.assertEqual(self.c.get('/api/visits',headers=self.h).json['counts']['completed'],1)
  self.assertEqual(self.c.get('/api/visits?history=1&q=Historical',headers=self.h).json['total'],1)
  self.assertEqual(self.c.get('/api/visits?history=1',headers=self.h).status_code,400)
 def test_staff_permissions_and_revocation(self):
  self.assertEqual(self.c.post('/api/users',headers=self.h,json={'name':'Staff Test','email':'staff@example.com','password':'staff-test-password'}).status_code,201)
  s=self.c.post('/api/login',json={'email':'staff@example.com','password':'staff-test-password'}).json
  sh={'Authorization':'Bearer '+s['token']}
  self.assertEqual(self.c.get('/api/users',headers=sh).status_code,403)
  self.assertEqual(self.c.get('/api/visits',headers=sh).status_code,200)
  self.c.patch('/api/users/'+str(s['user']['id']),headers=self.h,json={'active':False})
  self.assertEqual(self.c.get('/api/visits',headers=sh).status_code,401)
 def test_roles_duplicate_checkin_and_delete_permissions(self):
  visitor={'first_name':'Sample','last_name':'Visitor','email':'Sample@Example.com','phone':'9545550100','zip_code':'33301','visit_reason':'Badge Pickup'}
  self.assertEqual(self.c.post('/api/visits',json=visitor).status_code,201)
  visitor['email']=' sample@example.com '
  self.assertEqual(self.c.post('/api/visits',json=visitor).status_code,409)
  self.assertEqual(self.c.get('/api/visits?history=1&q=Sample',headers=self.h).json['total'],1)
  with app.app_context():
   visit_id=db().execute('SELECT id FROM visits').fetchone()[0]
   old=(datetime.now(timezone.utc)-timedelta(days=2)).isoformat()
   db().execute('UPDATE visits SET created_at=?',(old,));db().commit()
  self.assertEqual(self.c.post('/api/visits',json=visitor).status_code,201)
  for role in ('staff','management','admin'):
   email=role+'@example.com'
   self.assertEqual(self.c.post('/api/users',headers=self.h,json={'name':role,'email':email,'password':'test-role-password','role':role}).status_code,201)
   login=self.c.post('/api/login',json={'email':email,'password':'test-role-password'}).json
   h={'Authorization':'Bearer '+login['token']}
   self.assertEqual(self.c.get('/api/users',headers=h).status_code,200 if role=='admin' else 403)
   self.assertEqual(self.c.get('/api/visits',headers=h).status_code,200)
   if role=='staff': self.assertEqual(self.c.delete('/api/visits/'+str(visit_id),headers=h).status_code,403)
   if role=='management': self.assertEqual(self.c.delete('/api/visits/'+str(visit_id),headers=h).status_code,200)
   if role=='admin':
    with app.app_context(): remaining=db().execute('SELECT id FROM visits').fetchone()[0]
    self.assertEqual(self.c.delete('/api/visits/'+str(remaining),headers=h).status_code,200)
  self.assertEqual(self.c.post('/api/users',headers=self.h,json={'name':'Invalid','email':'invalid@example.com','password':'test-role-password','role':'root'}).status_code,400)
  users=self.c.get('/api/users',headers=self.h).json
  staff=next(u for u in users if u['role']=='staff')
  self.assertEqual(self.c.patch('/api/users/'+str(staff['id']),headers=self.h,json={'role':'management'}).status_code,200)
  primary=next(u for u in users if u['email']==ADMIN)
  self.assertEqual(self.c.patch('/api/users/'+str(primary['id']),headers=self.h,json={'role':'staff'}).status_code,400)
 def test_short_passwords_allowed_but_empty_rejected(self):
  self.assertEqual(self.c.post('/api/users',headers=self.h,json={'name':'Short password','email':'short@example.com','password':'abc','role':'staff'}).status_code,201)
  self.assertEqual(self.c.post('/api/users',headers=self.h,json={'name':'Empty password','email':'empty@example.com','password':''}).status_code,400)
  login=self.c.post('/api/login',json={'email':'short@example.com','password':'abc'}).json
  h={'Authorization':'Bearer '+login['token']}
  self.assertEqual(self.c.post('/api/password',headers=h,json={'current_password':'abc','new_password':''}).status_code,400)
  self.assertEqual(self.c.post('/api/password',headers=h,json={'current_password':'abc','new_password':'xy'}).status_code,200)
  self.assertEqual(self.c.post('/api/login',json={'email':'short@example.com','password':'xy'}).status_code,200)
 def test_visit_reason_required_and_saved(self):
  visitor={'first_name':'Reason','last_name':'Visitor','email':'reason@example.com','phone':'9545550100','zip_code':'33301'}
  self.assertEqual(self.c.post('/api/visits',json=visitor).status_code,400)
  visitor['visit_reason']='Invalid'
  self.assertEqual(self.c.post('/api/visits',json=visitor).status_code,400)
  from app import VISIT_REASONS
  for i,reason in enumerate(VISIT_REASONS):
   visitor.update(email=f'reason{i}@example.com',visit_reason=reason)
   self.assertEqual(self.c.post('/api/visits',json=visitor).status_code,201)
  rows=self.c.get('/api/visits?history=1&q=Reason',headers=self.h).json['items']
  self.assertEqual({r['visit_reason'] for r in rows},set(VISIT_REASONS))
if __name__=='__main__': unittest.main()
