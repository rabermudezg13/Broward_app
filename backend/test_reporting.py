import unittest
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
from io import BytesIO
import test_app
from app import app,db
from reporting import period_bounds

class ReportingTest(unittest.TestCase):
 setUp=test_app.FrontDeskTest.setUp
 def seed(self):
  tz=ZoneInfo('America/New_York')
  def add(first,email,date,reason):
   stamp=datetime.fromisoformat(date).replace(tzinfo=tz).astimezone(timezone.utc).isoformat()
   db().execute('INSERT INTO visits(first_name,last_name,email,phone,zip_code,visit_reason,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)',(first,'Example',email,'9545550100','03301',reason,stamp,stamp))
  with app.app_context():
   for i in range(55): add('=1+1' if i==0 else 'Test '+str(i),f'badge{i}@example.com','2026-11-02T09:00:00','Badge Pickup')
   add('Sunday','sunday@example.com','2026-11-08T12:00:00','Fingerprinting')
   add('Month end','end@example.com','2026-11-30T23:59:59','Other')
   add('Legacy','legacy@example.com','2026-11-01T00:00:00','')
   add('Before','before@example.com','2026-10-31T23:59:59','Badge Pickup')
   add('After','after@example.com','2026-12-01T00:00:00','Badge Pickup')
   db().commit()
 def test_periods_and_dst(self):
  start,end,begin,finish=period_bounds('day','2026-11-01')
  self.assertEqual((datetime.fromisoformat(finish)-datetime.fromisoformat(begin)).total_seconds(),25*3600)
  self.assertEqual(str(period_bounds('month','2024-02-29')[1]),'2024-03-01')
  self.assertEqual(str(period_bounds('week','2026-11-08')[0]),'2026-11-02')
 def test_statistics_and_report_scope(self):
  self.seed()
  self.assertEqual(self.c.get('/api/statistics').status_code,401)
  self.assertEqual(self.c.get('/api/reports/badge-pickup/export').status_code,401)
  r=self.c.get('/api/statistics?period=month&date=2026-11-12',headers=self.h).json
  self.assertEqual(r['total'],58);self.assertEqual(r['badge_pickup'],55);self.assertEqual(r['unique_visitors'],58)
  self.assertEqual(sum(x['total'] for x in r['categories']),58)
  self.assertEqual(next(x['total'] for x in r['categories'] if x['category']=='Not specified'),1)
  self.assertEqual(self.c.get('/api/statistics?period=week&date=2026-11-08',headers=self.h).json['total'],56)
  self.assertEqual(self.c.get('/api/statistics?period=day&date=2026-11-02',headers=self.h).json['total'],55)
  r=self.c.get('/api/reports/badge-pickup?period=month&date=2026-11-12&page=2',headers=self.h).json
  self.assertEqual(r['total'],55);self.assertEqual(len(r['items']),5)
  self.assertEqual(self.c.get('/api/statistics?period=year',headers=self.h).status_code,400)
  self.assertEqual(self.c.get('/api/statistics?period=month&date=2026-02-30',headers=self.h).status_code,400)
 def test_excel_pdf_and_empty_exports(self):
  from openpyxl import load_workbook
  self.seed()
  query='?period=month&date=2026-11-12&format='
  r=self.c.get('/api/reports/badge-pickup/export'+query+'xlsx',headers=self.h)
  self.assertEqual(r.status_code,200)
  ws=load_workbook(BytesIO(r.data)).active
  self.assertEqual(ws.max_row,61);self.assertEqual(ws['B7'].value,'=1+1');self.assertEqual(ws['B7'].data_type,'s');self.assertEqual(ws['F7'].value,'03301')
  r=self.c.get('/api/reports/badge-pickup/export'+query+'pdf',headers=self.h)
  self.assertEqual(r.status_code,200);self.assertTrue(r.data.startswith(b'%PDF'))
  r=self.c.get('/api/reports/badge-pickup/export?period=day&date=2026-09-01&format=xlsx',headers=self.h)
  self.assertIn('No Badge Pickup',load_workbook(BytesIO(r.data)).active['A7'].value)
  self.assertEqual(self.c.get('/api/reports/badge-pickup/export'+query+'csv',headers=self.h).status_code,400)
if __name__=='__main__': unittest.main()
