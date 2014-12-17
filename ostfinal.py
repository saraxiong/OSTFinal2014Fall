import os
import urllib
import cgi
import time

from google.appengine.api import users
from google.appengine.ext import db
from google.appengine.api import memcache
from google.appengine.api import mail

import jinja2
import webapp2
import re
import string
import datetime

JINJA_ENVIRONMENT = jinja2.Environment(
    loader=jinja2.FileSystemLoader(os.path.dirname(__file__)),
    extensions=['jinja2.ext.autoescape'],
    autoescape=True)

class Question(db.Model):
    name = db.StringProperty()
    content = db.TextProperty(default="")
    ownerid = db.StringProperty()
    ownername = db.StringProperty()
    quser = db.StringProperty()
    created_time = db.DateTimeProperty(auto_now_add=True)
    modify_time = db.DateTimeProperty(auto_now=True)
    voteuplist = db.ListProperty(str,indexed=False,default=[])
    votedownlist = db.ListProperty(str,indexed=False,default=[])
    up = db.IntegerProperty(default=0)
    down = db.IntegerProperty(default=0)
    diff = db.IntegerProperty(default=0)
    tags = db.ListProperty(db.Key)

    def tagList(self):
        return [Tag.get(key) for key in self.tags]
    def tagStr(self):
        return " ".join([Tag.get(x).tag for x in self.tags])
    def modifytimeEST(self):
        return self.modify_time + datetime.timedelta(hours=-5)    
    def contentFormat(self):
        return content_filter(self.content)
 
class Tag(db.Model):
    tag = db.StringProperty()
 

class Image(db.Model):
    image = db.BlobProperty()
    question = db.ReferenceProperty(Question, collection_name = 'images')
    contentType = db.StringProperty()
    

def content_filter(str):
    str = re.sub(r'(https?)(://[\w:;/.?%#&=+-]+)(\.(jpg|png|gif))', imageReplacer, str)
    str = re.sub(r'(?<!")(https?)(://[\w:;/.?%#&=+-]+)', urlReplacer, str)
    str = str.replace('\r\n', '\n')
    str = str.replace('\n','<br />\n')
    str = displayImages(str)
    return str

def urlReplacer(match, limit =40):
    return '<a href="%s">%s</a>' % (match.group(), match.group()[:limit] + ('...' if len(match.group()) > limit else ''))

def imageReplacer(match):
    return '<div><image src="%s" alt="loading image.."></div>' % match.group()

def displayImages(str):
    return re.sub(r'\[img:(.*)\]', r'<img src="/image/\1" style="max-width:400px">', str)
    
class Answer(db.Model):
    content = db.TextProperty(default = "")
    ownerid = db.StringProperty()
    ownername = db.StringProperty()
    created_time = db.DateTimeProperty(auto_now_add=True)
    modify_time = db.DateTimeProperty(auto_now=True)
    voteuplist = db.ListProperty(str,indexed=False,default=[])
    votedownlist = db.ListProperty(str,indexed=False,default=[])
    up = db.IntegerProperty(default=0)
    down = db.IntegerProperty(default=0)
    diff = db.IntegerProperty(default=0)
    def modifytimeEST(self):
        return self.modify_time + datetime.timedelta(hours=-5)
    def contentFormat(self):
        return content_filter(self.content)

class MainPage(webapp2.RequestHandler):
    
    def get(self):
        questions = Question.all()        
        questions.order("-created_time")
        user = users.get_current_user()
        
        tag_list = []
        for question in questions:
           for tag in question.tagList():
               if tag_list:
                  isTagExist = False
                  for item in tag_list:
                      if item.tag == tag.tag:
                           isTagExist = True
                           break
                  if not isTagExist:
                      tag_list.append(tag)
               else:
                  tag_list.append(tag)
 
        cursor = self.request.get('cursor')
        if cursor:
           questions.with_cursor(start_cursor=cursor)
        items = questions.fetch(10)
        if len(items) < 10:
            cursor = None
        else:
            cursor = questions.cursor()

        if user:
            url = users.create_logout_url(self.request.uri)
            url_linktext = 'Welcome ' + user.nickname() + ' -> Logout'
        else:
            url = users.create_login_url(self.request.uri)
            url_linktext = 'Login'

        template_values = {
            'questions': items,
            'cursor': cursor,
            'taglist': tag_list,
            'url': url,
            'url_linktext': url_linktext,
        }

        template = JINJA_ENVIRONMENT.get_template('/template/mainpage.html')
        self.response.write(template.render(template_values))

class UploadImage(webapp2.RequestHandler):
    def get(self):
        images=Image.all()
        template = JINJA_ENVIRONMENT.get_template('/template/uploadimage.html')
        self.response.write(template.render({'images' : images}))
    def post(self):
        if self.request.get('file'):
            image = Image()
            image.image = self.request.POST.get('file').file.read()
            image.contentType = self.request.body_file.vars['file'].headers['content-type']
            image.put()
        self.redirect('/uploadimage') 

class TagHandler(webapp2.RequestHandler):
    def get(self, tagkey):
        tag = Tag.get(tagkey)          
        questions = Question.all()       
        questions.filter('tags', tag.key())
        questions.order("-created_time")         
        tag_list = []
        tag_list.append(tag)
 
        cursor = self.request.get('cursor')
        if cursor: 
            questions.with_cursor(start_cursor=cursor)
        items = questions.fetch(10)
        if len(items) < 10:      
            cursor = None    
        else:
            cursor = questions.cursor()
        template_values = {'questions': items, 'cursor': cursor, 'taglist' : tag_list}    
        template = JINJA_ENVIRONMENT.get_template('/template/mainpage.html')
        self.response.write(template.render(template_values))


class AddQuestion(webapp2.RequestHandler):
    def get(self):
        user = users.get_current_user()
        if user:
            template = JINJA_ENVIRONMENT.get_template('/template/addquestion.html')
            self.response.write(template.render())
        else:
            self.redirect(users.create_login_url('/')) 
             
    def post(self):
        user = users.get_current_user()        
        question = Question()
        question.name = self.request.get('name')
        question.content = self.request.get('content')
        question.ownerid = user.user_id()
        question.ownername = user.nickname()
        question.quser = user.email()
        question.created_time = question.created_time + datetime.timedelta(hours=-5)
        question.modify_time = question.modify_time + datetime.timedelta(hours=-5)
        tags = self.request.get('tags')
        if question.name and question.content:
              taglist = re.split('[,; ]+', tags)
              question.tags = []
              for tagstr in taglist:
                  tag = Tag.all().filter('tag =', tagstr).get()
                  if tag == None:
                      tag = Tag(tag=tagstr)
                      tag.put()
                  question.tags.append(tag.key())
              question.put()
              time.sleep(0.1)
        self.redirect('/')

class EditQuestion(webapp2.RequestHandler):
    def get(self, questionkey):
        user = users.get_current_user()
        question = Question.get_by_id(int(questionkey))
        if user:
           if user.user_id() == question.ownerid: 
              template = JINJA_ENVIRONMENT.get_template('/template/editquestion.html')
              self.response.write(template.render({'questionkey':questionkey,
                                                   'oldname':question.name,
                                                   'oldcontent':question.content,
                                                   'oldtags' :question.tagStr(),
                                                   'images' : question.images}))
           else:             
              template = JINJA_ENVIRONMENT.get_template('/template/error.html')
              self.response.write(template.render())
        else:
           self.redirect(users.create_login_url('/editquestion/%s' %questionkey))

    def post(self, questionkey):
        question = Question.get_by_id(int(questionkey))
        question.name = self.request.get('name')
        question.content = self.request.get('content')
        tags = self.request.get('tags')
        taglist = re.split('[,; ]+', tags)
        question.tags = []
        for tagstr in taglist:     
            tag = Tag.all().filter('tag =', tagstr).get()
            if tag == None:      
                tag = Tag(tag=tagstr)
                tag.put()
            question.tags.append(tag.key())
        
        if self.request.get('file'):
            image = Image()
            image.image = self.request.POST.get('file').file.read()
            image.contentType = self.request.body_file.vars['file'].headers['content-type']
            image.question = question
            image.put()
            question.content = question.content + '\n' + '[img:%s]' % image.key() + '\n'
        question.put()
        time.sleep(0.1)
        self.redirect('/questionview/%s' %questionkey)

class ImageHandler(webapp2.RequestHandler):
    def get(self, imagekey):
        image = getImage(imagekey)
        self.response.headers['Content-Type'] = image.contentType.encode('utf-8')
        self.response.out.write(image.image)

def getImage(key):
    data = memcache.get(key)
    if data == None:
        data = db.get(key)
        memcache.set(key = key, value = data, time=3600)
    return data    

class View(webapp2.RequestHandler):
    def get(self, questionkey):
        parentquestion = Question.get_by_id(int(questionkey))
        answers = Answer.all()
        answers.ancestor(parentquestion)
        answers.order("-diff")
        user = users.get_current_user()
        if user:
            url = users.create_logout_url(self.request.uri)
            url_linktext = 'Welcome ' + user.nickname() + ' -> Logout'
        else:
            url = users.create_login_url(self.request.uri)
            url_linktext = 'Login'

        template_values = {
            'questionkey': questionkey,
            'answers': answers,
            'parentquestion': parentquestion,
            'url': url,
            'url_linktext': url_linktext,
        }         
       
        template = JINJA_ENVIRONMENT.get_template('/template/questionview.html')
        self.response.write(template.render(template_values))

class AddAnswer(webapp2.RequestHandler):
    def get(self, questionkey):
        user = users.get_current_user()
        parentquestion = Question.get_by_id(int(questionkey))

        if user:
            template = JINJA_ENVIRONMENT.get_template('/template/addanswer.html')
            self.response.write(template.render({'questionkey': questionkey}))
        else:
            self.redirect(users.create_login_url('/questionview/%s' %questionkey))
         
    def post(self, questionkey):
        parentquestion = Question.get_by_id(int(questionkey))
        
        content = self.request.get('content')
        user = users.get_current_user()
        ownerid = user.user_id()
        ownername = user.nickname()
        senderemail=user.email()       
        answer = Answer(parent = parentquestion, content=content, ownerid=ownerid,ownername=ownername)
        answer.created_time = answer.created_time + datetime.timedelta(hours=-5)
        answer.put()
        time.sleep(0.1)
        
        message = mail.EmailMessage()
        message.sender = user.email()
        message.subject = "You question has been answered!!"
        message.to = parentquestion.quser
        message.body = """
                      Your question has been answered. Please check it!!"""
        message.send() 
        self.redirect('/questionview/%s' %questionkey) 

class EditAnswer(webapp2.RequestHandler):
    def get(self, questionkey, answerkey):
        user = users.get_current_user()
        parentquestion = Question.get_by_id(int(questionkey))
        answer = Answer.get_by_id(int(answerkey),parent = parentquestion)

        if user:
           if user.user_id() == answer.ownerid:
              template = JINJA_ENVIRONMENT.get_template('/template/editanswer.html')
              self.response.write(template.render({'questionkey':questionkey,
                                                   'answerkey':answerkey,
                                                   'oldcontent':answer.content}))
           else:
              template = JINJA_ENVIRONMENT.get_template('/template/error.html')
              self.response.write(template.render())
        else:
           self.redirect(users.create_login_url('/editanswer/%s/%s' %(questionkey,answerkey)))

    def post(self, questionkey, answerkey):
        parentquestion = Question.get_by_id(int(questionkey))
        answer = Answer.get_by_id(int(answerkey),parent = parentquestion)
        answer.content = self.request.get('content')
        answer.put()
        time.sleep(0.1)
        self.redirect('/questionview/%s' %questionkey)


class Vote(webapp2.RequestHandler):
    def get(self,type,vote,questionkey,answerkey):
        if type=='question':
           user = users.get_current_user()
           votequestion = Question.get_by_id(int(questionkey))
      
           if vote=='up':
              if user:
                 userid = user.user_id()
        
                 if userid in votequestion.voteuplist:
                   self.redirect('/questionview/%s' %questionkey)  
                 else:
                   votequestion.voteuplist.append(userid)
                   votequestion.up = votequestion.up + 1
                   votequestion.diff = votequestion.up - votequestion.down
                   votequestion.put()
                   time.sleep(0.1)
                   self.redirect('/questionview/%s' %questionkey)
              else:
                 self.redirect(users.create_login_url('/questionview/%s' %questionkey))

           if vote=='down':
              if user:
                 userid = user.user_id()

                 if userid in votequestion.votedownlist:
                   self.redirect('/questionview/%s' %questionkey)
                 else:
                   votequestion.votedownlist.append(userid)
                   votequestion.down = votequestion.down + 1
                   votequestion.diff = votequestion.up - votequestion.down
                   votequestion.put()
                   time.sleep(0.1)
                   self.redirect('/questionview/%s' %questionkey)
              else:
                 self.redirect(users.create_login_url('/questionview/%s' %questionkey))
        
        elif type=='answer':
           user = users.get_current_user()
           parentquestion = Question.get_by_id(int(questionkey))
           voteanswer = Answer.get_by_id(int(answerkey),parent=parentquestion)
          
        

           if vote=='up':
              if user:
                 userid = user.user_id()

                 if userid in voteanswer.voteuplist:
                   self.redirect('/questionview/%s' %questionkey)
                 else:
                   voteanswer.voteuplist.append(userid)
                   voteanswer.up = voteanswer.up + 1
                   voteanswer.diff = voteanswer.up - voteanswer.down
                   voteanswer.put()
                   time.sleep(0.1)
                   self.redirect('/questionview/%s' %questionkey)
              else:
                 self.redirect(users.create_login_url('/questionview/%s' %questionkey))

           if vote=='down':
              if user:
                 userid = user.user_id()

                 if userid in voteanswer.votedownlist:
                   self.redirect('/questionview/%s' %questionkey)
                 else:
                   voteanswer.votedownlist.append(userid)
                   voteanswer.down = voteanswer.down + 1
                   voteanswer.diff = voteanswer.up - voteanswer.down
                   voteanswer.put()
                   time.sleep(0.1)
                   self.redirect('/questionview/%s' %questionkey)
              else:
                 self.redirect(users.create_login_url('/questionview/%s' %questionkey)) 

class RSS(webapp2.RequestHandler):
    def get(self, questionkey):
        parentquestion = Question.get_by_id(int(questionkey))
        answers = Answer.all()
        answers.ancestor(parentquestion)
        answers.order("-created_time")
        template = JINJA_ENVIRONMENT.get_template('/template/rss.xml')
        self.response.headers['Content-Type'] = 'application/rss+xml'
        self.response.write(template.render({'parentquestion': parentquestion,
                                             'answers' : answers}))

application = webapp2.WSGIApplication([
    ('/', MainPage),
    ('/addquestion', AddQuestion),
    ('/questionview/(.*)', View),
    ('/addanswer/(.*)', AddAnswer), 
    ('/vote/(.*)/(.*)/(.*)/(.*)', Vote),
    ('/editquestion/(.*)',EditQuestion), 
    ('/editanswer/(.*)/(.*)',EditAnswer),
    ('/tag/(.*)',TagHandler),
    ('/image/(.*)',ImageHandler), 
    ('/uploadimage',UploadImage),
    ('/rss/(.*)', RSS),
], debug=True)
