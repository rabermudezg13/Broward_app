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
  with app.app_context():
   db().execute('DELETE FROM visits');db().execute('DELETE FROM sessions');db().execute("DELETE FROM users WHERE role='staff'");db().commit()
  r=self.c.post('/api/login',json={'email':ADMIN,'password':'test-only-strong-password'})
  self.h={'Authorization':'Bearer '+r.json['token']}
 def test_checkin_privacy_and_validation(self):
  self.assertEqual(self.c.get('/api/visits').status_code,401)
  self.assertEqual(self.c.post('/api/visits',json={}).status_code,400)
  self.assertEqual(self.c.post('/api/visits',json={'first_name':'Test','last_name':'Visitor','email':'test@example.com','phone':'9545550100','zip_code':'33301'}).status_code,201)
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
if __name__=='__main__': unittest.main()
