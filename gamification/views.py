
import json
import os
import shutil
import zipfile
import xml.dom.minidom

from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponse, JsonResponse, HttpResponseRedirect
from django.shortcuts import render, get_object_or_404
from django.urls import reverse
from django.utils import timezone

from gamification.default_points import *
from gamification.forms import EditCoursePointsForm, EditActivityPointsForm
from gamification.models import *
from oppia.models import Points, Course, Section, Activity
from oppia.permissions import *

from pydoc import doc
from platform import node


@staff_member_required
def leaderboard_export(request, course_id=None):

    if request.is_secure():
        prefix = 'https://'
    else:
        prefix = 'http://'

    response_data = {}
    response_data['generated_date'] = timezone.now()
    response_data['server'] = prefix + request.META['SERVER_NAME']

    if course_id is None:
        leaderboard = Points.get_leaderboard()
    else:
        course = get_object_or_404(Course, pk=course_id)
        leaderboard = Points.get_leaderboard(course=course)
        response_data['course'] = course.shortname

    response_data['leaderboard'] = []

    for idx, leader in enumerate(leaderboard):
        leader_data = {}
        leader_data['position'] = idx + 1
        leader_data['username'] = leader.username
        leader_data['first_name'] = leader.first_name
        leader_data['last_name'] = leader.last_name
        leader_data['points'] = leader.total
        leader_data['badges'] = leader.badges
        response_data['leaderboard'].append(leader_data)

    return JsonResponse(response_data)

def edit_course_points(request, course_id):
    if not can_edit_course(request, course_id):
        raise exceptions.PermissionDenied
    
    course = Course.objects.get(id=course_id)
    doc = get_module_xml(course, 'r')
    current_points = load_course_points(request, doc, course)  
    
    if request.method == 'POST':
        form = EditCoursePointsForm(request.POST, initial = current_points)
        if form.is_valid():
            save_course_points(request, form, course)
            
            return HttpResponseRedirect(reverse('oppia_gamification_course_points_updated', args=[course.id]))  # Redirect after POST
    else:
        form = EditCoursePointsForm(initial = current_points)

    return render(request, 'oppia/gamification/edit-course-points.html',
                              {'course': course,
                                  'form': form })

def course_points_updated(request, course_id):
    if not can_edit_course(request, course_id):
        raise exceptions.PermissionDenied
    course = Course.objects.get(id=course_id)
    return render(request, 'oppia/gamification/course-points-updated.html',
                              {'course': course })


def view_activity_points(request, course_id):
    if not can_edit_course(request, course_id):
        raise exceptions.PermissionDenied
    
    course = Course.objects.get(id=course_id)
    sections = Section.objects.filter(course=course).order_by('order')
    
    return render(request, 'oppia/gamification/view-activity-points.html',
                              {'course': course,
                               'sections': sections })

def edit_activity_points(request, course_id, activity_id):
    if not can_edit_course(request, course_id):
        raise exceptions.PermissionDenied
    
    course = Course.objects.get(id=course_id)
    activity = Activity.objects.get(id=activity_id)
    
    if request.method == 'POST':
        form = EditActivityPointsForm(request.POST, initial = activity.get_event_points()['events'])
        if form.is_valid():
            save_activity_points(request, form, course, activity)
            return HttpResponseRedirect(reverse('oppia_gamification_view_activity_points', args=[course_id]))  # Redirect after POST
    else:
        form = EditActivityPointsForm(initial = activity.get_event_points()['events'])
    
    return render(request, 'oppia/gamification/edit-activity-points.html',
                              {'course': course,
                               'activity': activity,
                               'form': form })
    
def load_course_points(request, doc, course):
    course_points = []
    gamification_node = get_course_gamification_node(doc)
    if gamification_node:
        for event in gamification_node.getElementsByTagName("event"):
            event_points = {}
            event_points['event'] = event.getAttribute("name")
            event_points['points'] = event.firstChild.nodeValue
            course_points.append(event_points)
        return course_points
    else:
        initialise_course_points(request, course, OPPIA_DEFAULT_POINTS)
        return OPPIA_DEFAULT_POINTS

def save_course_points(request, form, course):
    
    doc = get_module_xml(course, 'a')
    
    gamification_node = get_course_gamification_node(doc)
    
    if gamification_node:
        for x in form.cleaned_data:
            for event in gamification_node.getElementsByTagName("event"):
                if event.getAttribute("name") == x:
                    event.firstChild.nodeValue = form.cleaned_data[x]
    else:
        meta = doc.getElementsByTagName("meta")[:1][0]
        gamification = doc.createElement("gamification")
        for x in form.cleaned_data:
            event = doc.createElement("event")
            event.setAttribute("name", x)
            value = doc.createTextNode(str(form.cleaned_data[x]))
            event.appendChild(value)
            gamification.appendChild(event)
        meta.appendChild(gamification)
    
    # update the gamification tables
    CourseGamificationEvent.objects.filter(course=course).delete()
    for x in form.cleaned_data:
        course_game_event = CourseGamificationEvent()
        course_game_event.user = request.user
        course_game_event.course = course
        course_game_event.event = x
        course_game_event.points = form.cleaned_data[x]
        course_game_event.save()
    
    rewrite_zip_file(request, course, doc)

def save_activity_points(request, form, course, activity):
    
    doc = get_module_xml(course, 'a')
    
    add_gamification_node = False

    activity_nodes = doc.getElementsByTagName("activity")
    update_node = None
    
    for activity_node in activity_nodes:
        if activity_node.getAttribute("digest") == activity.digest:
            update_node = activity_node            
    if update_node == None:
        return
    
    try:
        for x in form.cleaned_data:
            for event in update_node.getElementsByTagName("gamification")[:1][0].getElementsByTagName("event"):
                if event.getAttribute("name") == x:
                    event.firstChild.nodeValue = form.cleaned_data[x]
    except IndexError: #xml does not have the gamification/events tag/s
        add_gamification_node = True

    if add_gamification_node:
        gamification = doc.createElement("gamification")
        for x in form.cleaned_data:
            event = doc.createElement("event")
            event.setAttribute("name", x)
            value = doc.createTextNode(str(form.cleaned_data[x]))
            event.appendChild(value)
            gamification.appendChild(event)
        update_node.appendChild(gamification)
    
    # update the gamification tables
    ActivityGamificationEvent.objects.filter(activity=activity).delete()
    for x in form.cleaned_data:
        activity_game_event = ActivityGamificationEvent()
        activity_game_event.user = request.user
        activity_game_event.activity = activity
        activity_game_event.event = x
        activity_game_event.points = form.cleaned_data[x]
        activity_game_event.save()
            
    rewrite_zip_file(request, course, doc)


def get_module_xml(course, mode): 
    course_zip_file = os.path.join(settings.COURSE_UPLOAD_DIR, course.filename)
    zip = zipfile.ZipFile(course_zip_file, mode)
    xml_content = zip.read(course.shortname + "/module.xml")
    zip.close()
    doc = xml.dom.minidom.parseString(xml_content)
    return doc

def get_course_gamification_node(doc):
    meta = doc.getElementsByTagName("meta")[:1][0]
    for node in meta.childNodes:
        if node.nodeType == node.ELEMENT_NODE and node.tagName == 'gamification':
            return node
    return None
  
def rewrite_zip_file(request, course, doc):
    temp_zip_path = os.path.join(settings.COURSE_UPLOAD_DIR, 'temp', str(request.user.id))
    module_xml = course.shortname + '/module.xml'
    try:
        os.makedirs(temp_zip_path)
    except OSError:
        pass # leaf dir for user id already exists
    
    course_zip_file = os.path.join(settings.COURSE_UPLOAD_DIR, course.filename)
    remove_from_zip(course_zip_file, temp_zip_path, course.shortname, module_xml)
    
    with zipfile.ZipFile(course_zip_file, 'a') as z:
        z.writestr(module_xml, doc.toprettyxml(indent='',newl='\n'))
       
def remove_from_zip(zipfname, temp_zip_path, course_shortname, *filenames):
    try:
        tempname = os.path.join(temp_zip_path, course_shortname +'.zip')
        with zipfile.ZipFile(zipfname, 'r') as zipread:
            with zipfile.ZipFile(tempname, 'w') as zipwrite:
                for item in zipread.infolist():
                    if item.filename not in filenames:
                        data = zipread.read(item.filename)
                        zipwrite.writestr(item, data)
        shutil.copy(tempname, zipfname)
    finally:
        shutil.rmtree(temp_zip_path)

def initialise_course_points(request, course, course_points):
    CourseGamificationEvent.objects.filter(course=course).delete()
    for event in course_points:
        course_game_event = CourseGamificationEvent()
        course_game_event.user = request.user
        course_game_event.course = course
        course_game_event.event = event['event']
        course_game_event.points = event['points']
        course_game_event.save()
