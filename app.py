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
from shacoof.misc_utils import to_object, debug_print
from shacoof.SQLiteUtil import create_connection, create_table
import logging
import sqlite3
from sqlite3 import Error

server="https://jira.devfactory.com/rest/api/latest/"
htmlbr = '<br>'

issue_db = []
progress_made = "0"
JIRA_DB = 'JIRA-DB.db'

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
   # input : list of issues, link_anme 
   # output : list of links of type link_name

   debug_print(app.logger,"FilterBy= "+filter_by + " Filter = "+name)
   result = []
   for issue in issue_list:
      res = get_issue_links(issue,filter_by,name)
      result += res
      debug_print(app.logger,issue.key + " || " + issue.fields.issuetype.name + " || " +  issue.fields.status.name  + " || " + str(len(res))  )

   #always remove the excessive trailing comma (,)
   return result

def get_issue_links(issue,filter_by, name):
   # input : list of issues, link_anme 
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
   cred =  "Basic " + base64.b64encode(b'scohenofir:JennyXO123!').decode("utf-8") 
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

app = Flask(__name__)
logging.basicConfig(filename='app.log', level=logging.DEBUG)
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
      debug_print(app.logger,e)
      return jsonify(result='Good')
   
   return jsonify(result='Bad')

@app.route("/populateDB/",methods = ['POST'])
def populateDB():

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

   #ActionItem add a check if the table exists and if so ask the user whether he wants to delete it 

   sql_create_tbl = """CREATE TABLE IF NOT EXISTS """+ query_name +""" (
                                    key text PRIMARY KEY,
                                    project text ,
                                    issue_type text ,
                                    created text
                                );"""



   if conn is None:
        debug_print(app.logger, "Error! cannot create the database connection.")
        return ("Error! cannot create the database connection.")

   create_table(conn,sql_create_tbl)
   progress_made = "20"   
   
   fields='key,project,issuetype,created'   
   maxResults=100
   startAt = 0 
   url = server + "search?jql="+ jql +"&startAt="+str(startAt)+"&maxResults="+str(maxResults) +"&fields="+fields
   result=execute_JIRA_RestAPI(url)
   issueList = [(i.key, i.fields.project.name, i.fields.issuetype.name, i.fields.created[0:10]) for i in result.issues]   
   while startAt+maxResults < result.total:
      startAt += maxResults
      progress_made = str(20+round((startAt/result.total)*80))   
      url = server + "search?jql="+ jql +"&startAt="+str(startAt)+"&maxResults="+str(maxResults) +"&fields="+fields
      result=execute_JIRA_RestAPI(url)
      issueList += [(i.key, i.fields.project.name, i.fields.issuetype.name, i.fields.created[0:10]) for i in result.issues]

   try:
      c = conn.cursor()
      #c.execute ('Delete from JIRA_QUERY')
      c.executemany ('INSERT INTO '+query_name+' VALUES (?,?,?,?)', issueList)
      conn.commit()
      conn.close()
      debug_print (app.logger,'issues created successfully')
   except Error as e:
      debug_print(app.logger, str(e))

   return "db populated successfully !!"

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

if __name__ == '__main__':
   app.run(debug = True,host='0.0.0.0')
   app.logger()