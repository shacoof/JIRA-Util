from flask import Flask, render_template, request, Response,jsonify
import collections
import traceback
import requests
import json
import base64
import sys
import os
import time
from datetime import datetime
from shacoof.misc_utils import to_object, debug_print, createCSV
from shacoof.SQLiteUtil import create_connection, create_table
import logging
import sqlite3
from sqlite3 import Error
import mysql.connector

server="https://jira.devfactory.com/rest/api/latest/"
htmlbr = '<br>'

issue_db = []
progress_made = "0"
JIRA_DB = 'JIRA-DB.db'


def retrieveFields(obj, fields): 
  f = fields.split(",");
  ret = [];
  for i in range(len(f)):
    try:
      if f[i] == "issuetype" :
        ret.append(obj.fields.issuetype.name)
      elif f[i] == "key":
        ret.append(obj.key)
      elif f[i] == "project":
        ret.append(obj.fields.project.name)
      elif f[i] == "status":
        ret.append(obj.fields.status.name)
      elif f[i] == "customfield_23602": # engineering vp
        ret.append(obj.fields["customfield_23602"].value.emailAddress)
      elif f[i] == "customfield_16405":  #engineering vp
        ret.append(obj.fields["customfield_16405"].value.emailAddress)
      elif f[i] == "customfield_16403": # Product CA
        ret.append(obj.fields["customfield_16403"].value.displayName)
      elif f[i] == "customfield_51006": #FunctionalPCA 
        ret.append(obj.fields["customfield_51006"].value.displayName)
      elif f[i] == "assignee":
        ret.append(obj.fields.assignee.displayName)
      elif f[i] == 'customfield_58100' : #distanceToRelease
         ret.append(obj.fields.customfield_58100)
      elif f[i] == 'customfield_60501' : #E2Es to complete BR
         ret.append(obj.fields.customfield_60501)
      else :
        ret.append(obj.fields[f[i]])
    except Error as e:
      debug_print(app.logger,e)
      ret += "no value"

  return ret

# recursion to find dependency tree 
# issue_list : list of JIRA keys 
# dependent_list : the return value, start by sending []
def find_dependencies(issue_list,dependent_list):            
   debug_print(app.logger,"-----> List to check = " + ",".join(issue_list))
   if len(issue_list) == 0 :
      debug_print(app.logger,"-----> Empty List")
      return
   elif len(issue_list) == 1:
      debug_print(app.logger,"-----> 1 to check = " + ",".join(issue_list))
      # get the issue
      url = server + "issue/"+ issue_list[0]
      issue = execute_JIRA_RestAPI(url)
      # get all depends on issues 
      dependent_links = get_issue_links(issue,"linkType","Depends On")
      # find only the ones that were not know before 
      new_links = [item for item in dependent_links if item not in dependent_list  ]
      if len(new_links)!=0:
         # recursively search the new ones for more dependents 
         find_dependencies(new_links,dependent_list)
         # the new ones added to the know list 
         dependent_list+=new_links
      return
   else:
      for i in issue_list:
         debug_print(app.logger,"-----> new candidate = "+i)
         if i not in dependent_list: 
            l = []
            l.append(i)           
            find_dependencies(l,dependent_list)
      return

def get_linked_issues_by_filter (issue_list,filter_by,name):
   # input : list of issues, link_name 
   # output : list of links of type link_name
   # uses get_issue_links to find the links, this is a wrapper to traverse all the issues in the list 

   debug_print(app.logger,"FilterBy= "+filter_by + " Filter = "+name)
   result = []
   for issue in issue_list:
      res = get_issue_links(issue,filter_by,name)
      result += res
      debug_print(app.logger,issue.key + " || " + issue.fields.issuetype.name + " || " +  issue.fields.status.name  + " || " + str(len(res))  )

   #always remove the excessive trailing comma (,)
   return result

def get_issue_links(issue,filter_by, name):
   """
    issue: issue object 
    filter_by: [linkType, issueType]
    name: name of link, e.g. "is blocked by"
   """
   #  input : issue, link_name 
   # output : list of links of type link_name
   global issue_db
   result = []
   for link in issue.fields.issuelinks:
      
      if hasattr(link, "outwardIssue"):
         issue_type = link.outwardIssue.fields.issuetype.name         
         key = link.outwardIssue.key         
         status = link.outwardIssue.fields.status.name
         link_type = link.type.outward
      if hasattr(link, "inwardIssue"):
         issue_type = link.inwardIssue.fields.issuetype.name
         key = link.inwardIssue.key
         status = link.inwardIssue.fields.status.name
         link_type = link.type.inward
      if (((link_type.lower() == name.lower() and filter_by=="linkType") or (issue_type==name and filter_by=="issueType"))\
                                                                            and status != 'Cancelled'):
         result.append(key)
      
      i={'key':key,'type':issue_type,'status':status}
      if i not in issue_db: issue_db.append(i)    
      debug_print(app.logger,"Key= "+key+ " || issueType = "  + issue_type+ " || Linktype = "  + link_type + " || Status = " + status)
   return result

def execute_JIRA_RestAPI(url):
   # execute the call to JIRA
   # input : url for the rest API
   # return : object (from JIRA response)
   debug_print (app.logger,'start jira query'+ datetime.now().ctime() )
   # Base encode email and api token
   #cred =  "Basic " + base64.b64encode(b'scohenofir:TigerXO123!').decode("utf-8") 
   cred =  "Basic " +'c2NvaGVub2ZpcjpUaWdlclhPMTIzIQ=='
   # used a service to convert string to base64 string is scohenofir:pwd


   print(cred)
   # Set header parameters
   headers = {
      "Accept": "application/json",
      "Content-Type": "application/json",
      "Authorization" : cred
   }

   # Send request and get response
   response = requests.request(
      "GET", 
      url,
      headers=headers
   )
   if response.status_code != 200:
      raise Error(str(response.status_code) + " :: "+response.text)
   # Decode Json string to Python
   json_str = json.loads(response.text)
   obj = to_object(json_str)
   debug_print (app.logger,'end jira query'+ datetime.now().ctime())
   return obj



logging.basicConfig(filename='app.log', level=logging.DEBUG,filemode='w')
logging.getLogger("myLogger")
app = Flask(__name__)
debug_print(app.logger,"Good morning sharon")

@app.route('/progress')
def progress():
   global progress_made
   val =  "data:" + str(progress_made) + "\n\n"
   #debug_print(app.logger,">>>>>>>> In progress "+val)
   return Response(val, mimetype= 'text/event-stream')

@app.route('/mainForm/')
def mainForm():
   global progress_made
   progress_made = 0 
   return render_template('mainForm.html')

@app.route("/hello/",methods = ['POST'])
def hello():
   name = request.form['name']
   return "hello {} !".format(name)

@app.route("/validate/")
def validate():
   
   try:
      query_name = request.args.get('query_name', 0, type=str)
   except Error as e:
      debug_print(app.logger,e)
      return "problem with parameters, expecting  query_name"

   full_db_name = os.path.join(app.root_path, JIRA_DB)
   conn = create_connection(full_db_name)
   cur = conn.cursor()

   try:
      cur.execute("SELECT * FROM "+ query_name)
      rows = cur.fetchall()
   except Error as e:
      debug_print(app.logger,str(e))
      return jsonify(result='Good')
   
   return jsonify(result='Bad')


@app.route("/backlogStat/",methods = ['POST'])
def backlogStat():
   global progress_made      
   progress_made = "0"   
   #get user parameters 
   try:
      query_name = request.form['query_name'].upper()
   except Error as e:
      debug_print(app.logger,e)
      return "problem with parameters, expecting  jql, fields and query_name"

   progress_made = "1"   
   # customfield_58100 DTR 
   # customfield_60501 E2Es to complete BR
   fields = 'key,project,issuetype,status,customfield_58100,customfield_60501'
   issueList = [['filter']+fields.split(',')] # setting the head row
   maxResults=1000
   jqls = [['WaitingCR','filter=141400'],['WaitingQaEnv','filter=141401'],['WaitingBR','filter=141406'],['preALP','filter=140006']]
   complete=0 #used to advance the bar
   for jql in jqls:      
      startAt = 0       
      while True: 
         # query next page 
         url = server + "search?jql="+ jql[1] +"&startAt="+str(startAt)+"&maxResults="+str(maxResults) +"&fields="+fields
         debug_print(app.logger, "URL="+url)
         result=execute_JIRA_RestAPI(url)
         # process records 
         for issue in result.issues:
            # get all issues 
            issueList += [([jql[0]]+retrieveFields(issue,fields))]
         
         progress_made = str(complete+round((startAt/(result.total+1)*(100/len(jqls)))))   # +1 incase 0
         startAt += maxResults
         if startAt > result.total:
            break
      complete +=24;
          

   createCSV(query_name,issueList)
   progress_made = '100'

   return render_template("message.html",message=str(result.total) + " issues retrieved successfully")


@app.route("/populateQueryByFields/",methods = ['POST'])
def populateQueryByFields():

   # Open DB
   # run a JQL
   # go through pages and upload records to DB
   # each query will create it's own table, if table exists it ask the user whether to delete the content 

   global progress_made      
   progress_made = "0"   
   #get user parameters 
   try:
      jql = request.form['jql']
      fields = request.form['fields'] #'key,project,issuetype,created'
      query_name = request.form['query_name'].upper()
   except Error as e:
      debug_print(app.logger,e)
      return "problem with parameters, expecting  jql, fields and query_name"

   progress_made = "1"   

   full_db_name = os.path.join(app.root_path, 'JIRA-DB.db')
   conn = create_connection(full_db_name)

   if conn is None:
        debug_print(app.logger, "Error! cannot create the database connection.")
        return ("Error! cannot create the database connection.")

   fld = fields.split(",")
   fldString=""
   insertString=""
   for i in fld:
      fldString += i + " TEXT,"
      insertString +="?,"
   issues_create_string = fldString[:-1]
   insertString=insertString[:-1]

   issues_table_name = query_name.strip()+"_ISSUES"
   sql_create_tbl = "CREATE TABLE IF NOT EXISTS "+ issues_table_name +"("+issues_create_string+");"
   create_table(conn,sql_create_tbl)
   debug_print(app.logger,"Issues table created")
   issueList = [(fld)]
   maxResults=100
   startAt = 0 
   while True: 
      # query next page 
      url = server + "search?jql="+ jql +"&startAt="+str(startAt)+"&maxResults="+str(maxResults) +"&fields="+fields
      debug_print(app.logger, "URL="+url)
      result=execute_JIRA_RestAPI(url)
      # process records 
      for issue in result.issues:
         # get all issues 
         issueList += [(retrieveFields(issue,fields))]
      
      progress_made = str(1+round((startAt/(result.total+1)*95)))   # +1 incase 0
      startAt += maxResults
      if startAt > result.total:
         break

   createCSV(query_name,issueList)
   progress_made = '100'
   #try:
   #   c = conn.cursor()
   #   cmd = 'INSERT INTO '+issues_table_name+' VALUES ('+insertString+')'
   #   c.executemany (cmd,issueList)
   #   conn.commit()
   #   conn.close()
   #   debug_print (app.logger,'issues created successfully')
   #except Error as e:
   #   var = traceback.format_exc()
   #   debug_print(app.logger, var)
   #   return (var)

   return render_template("FullIssueReport.html",
         issue_fields   = fld,
         issues         = issueList
         )


@app.route("/populateQuery/",methods = ['POST'])
def populateQuery():

   # Open DB
   # run a JQL
   # go through pages and upload records to DB
   # each query will create it's own table, if table exists it ask the user whether to delete the content 

   global progress_made      
   progress_made = "0"   
   #get user parameters 
   try:
      jql = request.form['jql']
      query_name = request.form['query_name'].upper()
   except Error as e:
      debug_print(app.logger,e)
      return "problem with parameters, expecting both jql and query_name"

   progress_made = "10"   

   full_db_name = os.path.join(app.root_path, 'JIRA-DB.db')
   conn = create_connection(full_db_name)

   if conn is None:
        debug_print(app.logger, "Error! cannot create the database connection.")
        return ("Error! cannot create the database connection.")

   issues_table_name = query_name.strip()+"_ISSUES"
   links_table_name = query_name.strip()+"_LINKS"
   histories_table_name = query_name.strip()+"_HISTORY"
   jql_queries_name = "JQL_QUERIES"

   issues_create_string = """  (KEY	TEXT,
                              PROJECT	TEXT,
                              CREATED	TEXT,
                              TYPE	TEXT
                           );"""

   Links_create_string =  """ (SOURCE_KEY	TEXT,
                              TARGET_KEY	TEXT,
                              LINK_TYPE	TEXT,
                              CREATED	TEXT
                           );"""

   histories_create_string = """ (
                                 KEY	TEXT,
                                 CHANGED_FIELD TEXT,
                                 FROM_STATUS	TEXT,
                                 TO_STATUS TEXT,
                                 CREATED	TEXT,
                                 HOURS_IN_STATUS	INTEGER
                           );"""

   jql_queries_create_string  = """   (
	                                    Name	TEXT,
	                                    JQL	TEXT
                                       ); """

   sql_create_tbl = "CREATE TABLE IF NOT EXISTS "+ issues_table_name +issues_create_string
   create_table(conn,sql_create_tbl)
   debug_print(app.logger,"Issues table created")

   sql_create_tbl = "CREATE TABLE IF NOT EXISTS "+ links_table_name +Links_create_string
   create_table(conn,sql_create_tbl)
   debug_print(app.logger,"Link table created")

   sql_create_tbl = "CREATE TABLE IF NOT EXISTS "+ histories_table_name +histories_create_string
   create_table(conn,sql_create_tbl)
   debug_print(app.logger,"histories table created")

   sql_create_tbl = "CREATE TABLE IF NOT EXISTS "+ jql_queries_name +jql_queries_create_string
   create_table(conn,sql_create_tbl)
   debug_print(app.logger,"jql queries table created")

   progress_made = "20"   
   historyList=[]
   issueList=[]
   linkList=[]
   fields='key,project,issuetype,created,issuelinks'   
    
   # Implementing do until loop : do until we reached the end of data 
   # see https://stackoverflow.com/questions/743164/emulate-a-do-while-loop-in-python
   maxResults=100
   startAt = 0 
   while True: 
      # query next page 
      url = server + "search?jql="+ jql +"&startAt="+str(startAt)+"&maxResults="+str(maxResults) +"&expand=changelog&fields="+fields
      debug_print(app.logger, "URL="+url)
      result=execute_JIRA_RestAPI(url)
      # process records 
      for issue in result.issues:
         # get all issues 
         issueList += [(issue.key, issue.fields.project.name, issue.fields.issuetype.name, issue.fields.created[0:10])]
         # for each issue get all its history / change log

         first_status_change = True
         
         for history in issue.changelog.histories:
            for item in history.items:
               if (item.field == 'status'):
                  if first_status_change:
                     historyList += [(issue.key,'status', item.fromString, item.toString, history.created,0)]
                     start_status_datetime = datetime.strptime(history.created[0:10]+history.created[11:16],"%Y-%m-%d%H:%M")
                     first_status_change = False
                  else:
                     end_status_datetime = datetime.strptime(history.created[0:10]+history.created[11:16],"%Y-%m-%d%H:%M")
                     delta = (end_status_datetime - start_status_datetime).total_seconds()/3600 # hours
                     start_status_datetime = end_status_datetime
                     historyList += [(issue.key,'status', item.fromString, item.toString, history.created,round(delta))]


               elif (item.field == 'Link' and (str(item.toString).find("is blocked by")>0 or str(item.fromString).find("is blocked by")>0) ):
                  historyList += [(issue.key,'link', item.fromString, item.toString, history.created,0)]
         # for each issue get all it's "is blocked by" liks 
         linkList += [[issue.key,i,"is blocked by",0] for i in get_issue_links(issue,"linkType","is blocked by")]
         #ActionItem calculate time in each state
         #ActionItem in order to calculate time in block state look at the history to know when the link was added 
      
      progress_made = str(20+round((startAt/(result.total+1)*80)))   # +1 incase 0
      # calculating next page starting point, if it's bigger then total results we are done, implementing do-unitl loop 
      # see https://stackoverflow.com/questions/743164/emulate-a-do-while-loop-in-python
      startAt += maxResults
      if startAt > result.total:
         break
      # if there is another page then it will be retrivied at the toop of the loop 
   try:
      c = conn.cursor()
      #c.execute ('Delete from JIRA_QUERY')
      c.execute      ('INSERT INTO JQL_QUERIES               VALUES(?,?)'         ,[query_name,jql])
      c.executemany  ('INSERT INTO '+issues_table_name+'     VALUES (?,?,?,?)'    ,issueList)
      c.executemany  ('INSERT INTO '+histories_table_name+'  VALUES (?,?,?,?,?,?)',historyList)
      c.executemany  ('INSERT INTO '+links_table_name+'      VALUES (?,?,?,?)'    ,linkList)
      conn.commit()
      conn.close()
      debug_print (app.logger,'issues created successfully')
   except Error as e:
      var = traceback.format_exc()
      debug_print(app.logger, var)
      return (var)

   return render_template("FullIssueReport.html",
         issue_fields   = ['Key','Product','Issue Type','Created'],
         issues         = issueList,
         link_fields    = ['Source Key','Target Key', 'Link Type', 'Created'],
         links          = linkList,
         history_fields = ['Key','Field','From value','To value', 'Date','Time in Status (Sec)'],
         histories      = historyList

         )

@app.route('/BRCalc/',methods = ['POST'])
def BRCalc():
   # logic is as follows
   # for each ticket
   #   Step 1 : find the E2E/s that test it (on the defect ticket)
   #   Step 2 : find these E2Es FAs
   #   Step 3 : find all E2Es (E1) that cover these FAs
   #   Step 4 : (recursively) find all E2Es (E2) that E1 are dependent on 
   try:
      global progress_made      
      progress_made = "0"
      debug_print(app.logger,"================= Start jira =================")  
      #get the main jira ticket/s
      jiraKey = request.form['jiraKey']
      debug_print(app.logger,"Jira Key ====> "+jiraKey)  
      url = server + "search?jql="+ " status not in (cancelled) and key in ("+ jiraKey + ")"
      debug_print(app.logger,"url  ====> "+ url)  
      issueList=execute_JIRA_RestAPI(url)
      progress_made = "20"
      # find all E2E that cover these tickets 
      end_to_end_links = get_linked_issues_by_filter(issueList.issues,"issueType","End-to-end Test")
      debug_print(app.logger,"E2E ====> "+','.join(end_to_end_links))

      #   Step 1 : find the E2E/s that test it (on the defect ticket)
      #get the E2E that tests it
      url = server + "search?jql="+ " status not in (cancelled) and key in ("+ ','.join(end_to_end_links) +")"
      E2E=execute_JIRA_RestAPI(url)
      progress_made = "40"
      #   Step 2 : find these E2Es FAs
      #          #get the E2Es' FAs
      FA_links =  get_linked_issues_by_filter(E2E.issues,"issueType","Functional Area")
      debug_print(app.logger,"FAs ====> "+','.join(FA_links))       
      progress_made = "60"
      #   Step 3 : find all E2Es (E1) that cover these FAs         
      #get all FAs tickets 
      url = server + "search?jql="+ " status not in (cancelled) and key in ("+ ','.join(FA_links) +")"
      debug_print(app.logger,"FAs E2Es ====> "+url)         
      FAs = execute_JIRA_RestAPI(url)
      #extract the E2Es that cover these FAs 
      FAs_E2Es_E1_links = get_linked_issues_by_filter(FAs.issues,"issueType","End-to-end Test")
      progress_made = "80"
      #   Step 4 : (recursively) find all E2Es (E2) that E1 are dependent on 
      #recursively search for all dependent E2Es, i.e. E2Es that are required in order to serve the original E2Es that cover the FA
      FAs_E2Es_E2_links = []
      find_dependencies(FAs_E2Es_E1_links,FAs_E2Es_E2_links)

      blast_radius = FAs_E2Es_E1_links
      blast_radius += [item for item in FAs_E2Es_E2_links if item not in blast_radius ]
      debug_print(app.logger,"blast_radius ====> " + str(len(blast_radius)) + "<br>" + "<br>".join(blast_radius))
      progress_made = "100"
   except Exception:
         var = traceback.format_exc()
         debug_print(app.logger,'================ Error ================>')
         debug_print(app.logger,var)
   finally:
      #return render_template('progress.html')  
      tbl_to_print = [ item for item in issue_db if item["key"] in blast_radius]
      return render_template('issueTable.html',issues=tbl_to_print)  

@app.route('/queryMySQL/',methods = ['POST'])
def queryMySQL():
   mydb = mysql.connector.connect(
   host="aurora5.aureacentral.com",
   user="scohenofir",
   password="3lJxymu26CRx8",
   database='jira'
   )

   print(mydb)
   mycursor = mydb.cursor()
   #mycursor.execute("select pname from project")
   mycursor.execute(
   """select concat(project.pkey,'-', jiraissue.issuenum),
		changeitem.OLDSTRING OldStatus, 
      changeitem.NEWSTRING NewStatus, 
      changegroup.CREATED Executed
      from changeitem 
      inner join changegroup  on changeitem.groupid = changegroup.id
      inner join jiraissue  on jiraissue.id = changegroup.issueid
      inner join project on project.id = jiraissue.project
      where changeitem.field ='status'
      and project.pkey = 'SLIFRONT'
   """)
   myresult = mycursor.fetchall()
   c = 0 
   for x in myresult:
      c+=1
      print(x)
      print (c)

@app.route('/ticketFieldHistory/',methods = ['POST'])
def ticketFieldHistory():
   try:
      global progress_made
      progress_made = "0"
      historyList = []      
      #get the main jira ticket/s
      jiraKey2 = request.form['jirakey2']   
      field_name = request.form['field']   
      url = server + "issue/"+ jiraKey2 +"?expand=changelog"
      progress_made = "40"
      issue=execute_JIRA_RestAPI(url)
      progress_made = "80"
      for history in issue.changelog.histories:
         for item in history.items:
            if (item.field == field_name):
               historyList.append({'field':field_name, 'from':item.fromString, 'to':item.toString,'date':history.created[0:10]})
      progress_made = "100"
   except Exception:
      var = traceback.format_exc()
      debug_print(app.logger,'================ Error ================>')
      debug_print(app.logger,var)
   finally: 
      return render_template('issueHistory.html',fields=['field name','from','to','date'], history=historyList)

# Add all tickets of type Based on project-key and from-date
@app.route("/timeInStatus/",methods = ['POST'])
def timeInStatus():

   debug_print(app.logger,"=============> timeInStatus   <================")
   global progress_made      
   progress_made = "0"   
   #get user parameters 
   try:
      project_keys = []
      project_keys.append(request.form['project_key'])
      from_date = request.form['from_date']
      Issue_types = request.form['issue_types']
      debug_print(app.logger,"project_key="+project_keys[0])
      debug_print(app.logger,"from_date="+from_date)
      debug_print(app.logger,"Issue_types="+Issue_types) #ActionItem : split using "," and build SQL dynamically in case of multiple values
   except Error as e:
      debug_print(app.logger,e)
      return "problem with parameters, expecting both jql and query_name"

   progress_made_int = 2
   progress_made = str(progress_made_int)

   #Create SQLLite connect and table if need to 
   full_db_name = os.path.join(app.root_path, 'JIRA-DB.db')
   sqlLiteConn = create_connection(full_db_name)

   if sqlLiteConn is None:
        debug_print(app.logger, "Error! cannot create the database connection.")
        return ("Error! cannot create the database connection.")

   time_in_status_table_name = "TIME_IN_STATUS"

   time_in_status_create_string = """  (PROJECT	TEXT,
                                        ISSUE_TYPE	TEXT,
                                        KEY	TEXT,
                                        STATUS TEXT,
                                        FROM_STATUS	TEXT,
                                        TO_STATUS	TEXT,
                                        CREATED TEXT
                                    );"""

   sql_create_tbl = "CREATE TABLE IF NOT EXISTS "+ time_in_status_table_name +time_in_status_create_string
   create_table(sqlLiteConn,sql_create_tbl)
   debug_print(app.logger,"Time in status table created")

   progress_made_int = 4
   progress_made = str(progress_made_int)

   sqlLiteCursor = sqlLiteConn.cursor()

   #if ALL then bring all in model products, I have pre-uploaded them using CSV import
   if project_keys[0] == "ALL":
      sqlLiteCursor.execute("SELECT * FROM IN_MODEL_PRODUCTS")
      project_keys = sqlLiteCursor.fetchall()

   # Open MySql and execute query
   mydb = mysql.connector.connect(
      host="aurora5.aureacentral.com",
      user="scohenofir",
      password="3lJxymu26CRx8",
      database='jira'   )
   mycursor = mydb.cursor()

   for project_key in project_keys :
      progress_made_int += 90/len(project_keys)
      progress_made += str(round(progress_made_int))
      debug_print(app.logger, 'Processing product ' + project_key[0])
      #delete old history for this project 
      try:
         sql_cmd = "Delete from " + time_in_status_table_name + " where project = '" + project_key[0] +"'"
         sqlLiteCursor.execute (sql_cmd)
         debug_print (app.logger,'Old issues deleted successfully')
      except Error as e:
         var = traceback.format_exc()
         debug_print(app.logger, var)
         return (var)
      
      query_string = """select  project.pkey,
            issuetype.pname,
            concat(project.pkey,'-', jiraissue.issuenum),
            issuestatus.pname,
            changeitem.OLDSTRING OldStatus, 
            changeitem.NEWSTRING NewStatus, 
            changegroup.CREATED Executed
            from changeitem 
            inner join changegroup  on changeitem.groupid = changegroup.id
            inner join jiraissue  on jiraissue.id = changegroup.issueid
            inner join project on project.id = jiraissue.project
            inner join issuetype  ON issuetype.id = jiraissue.issuetype
            inner join issuestatus on issuestatus.id = jiraissue.issuestatus 
            where changeitem.field ='status'
            and ( issuetype.pname = 'Defect' or issuetype.pname = 'Customer Defect' )
            and jiraissue.CREATED > '""" + from_date + """'
            and project.pkey = '""" + project_key[0] + """'
            Order by project.pkey, jiraissue.issuenum, changegroup.CREATED
         """

      try:
         #debug_print (app.logger, query_string)
         mycursor.execute(query_string)
         records = mycursor.fetchall()         
         # [0] project [1] issue type [2] key [3] status  [4] from status [5] to status  [6] created
         sqlLiteCursor.executemany  ('INSERT INTO '+time_in_status_table_name+' VALUES (?,?,?,?,?,?,?)'    ,records)
         sqlLiteConn.commit()
         debug_print (app.logger,str(len(records))+' records created successfully')
      except Error as e:
         var = traceback.format_exc()
         debug_print(app.logger, var)
         return (var)

   sqlLiteConn.close()
   progress_made_int = 100
   progress_made = str(progress_made_int)
   return render_template('message.html',message='All records processed')

if __name__ == '__main__':
   app.run(debug = True,host='0.0.0.0')
   app.logger()