from flask import escape, abort, make_response, jsonify
import os
import firebase_admin
from firebase_admin import auth
import requests
from requests.structures import CaseInsensitiveDict
import json


class User:
    def __init__(self, firebase_uid=None):
        self.firebase_uid = firebase_uid.lower()

    # inner Class for Xooa user not found exception
    class XooaUserNotFound(Exception):
        """Raised when user not found in Xooa"""

        pass

    # get the user's Xooa token
    def get_xooa_user(self):
        # the FIreBase user's Xooa email is their FireBase UID suffixed by @firebase.com
        xooa_email = self.firebase_uid + "@firebase.com"

        # setup the header for our request to Xooa
        headers = CaseInsensitiveDict()
        headers["Accept"] = "application/json"
        headers["Authorization"] = "Bearer " + os.getenv("XOOA_API_KEY")

        # set the url for the Xooa get user by email endpoint
        url = "https://api.xooa.com/api/v2/app-users/get-by-email/"

        # find the user's Xooa UID by making a request to the Xooa API's get-by-email endpoint
        r = requests.get(
            +xooa_email,
            headers=headers,
        )
        # check if everything went ok
        try:
            r.raise_for_status()
        except requests.exceptions.HTTPError as e:
            # Whoops it wasn't a 200
            response = r.json()
            # if the exception was raise becuase a user doesn't exsit in Xooa by this email, then raise the custom XooaUserNotFound exception
            if response["error"] == "App User not found":
                raise self.XooaUserNotFound
            # for all other exceptions abort and respone with JSON error
            else:
                abort(make_response(jsonify(error=response["error"]), r.status_code))

        return r.json()

    # create a new user in Xooa that corresponds to a FireBase user
    def create_xooa_user(self):
        # get the Xooa role ID for the "NTF USER" role
        role_id = os.getenv("XOOA_NFT_USER_ROLE_ID")

        # the FIreBase user's Xooa email is their FireBase UID suffixed by @firebase.com
        xooa_email = self.firebase_uid + "@firebase.com"

        # set the url for the Xooa create user endpoint
        url = "https://api.xooa.com/api/v2/app-users"

        # setup the header for our request to Xooa
        headers = CaseInsensitiveDict()
        headers["Accept"] = "application/json"
        headers["Content-Type"] = "application/json"
        headers["Authorization"] = "Bearer " + os.getenv("XOOA_API_KEY")

        # setup our JSON body payload for our request
        payload = {"Name": self.firebase_uid, "Email": xooa_email, "Roles": [role_id]}

        # create the Xooa user by making a POST request to the Xooa API's create user endpoint
        r = requests.post(url, data=json.dumps(payload), headers=headers)
        # check if everything went ok
        try:
            r.raise_for_status()
        except requests.exceptions.HTTPError as e:
            # Whoops it wasn't a 200
            response = r.json()
            abort(make_response(jsonify(error=response["error"]), r.status_code))


# initialise FireBase
default_app = firebase_admin.initialize_app()

# the main/trigger function
def firebase_xooa_connector(request):
    # grab the ID Token from the header
    id_token = request.headers["Authorization"].split(" ").pop()

    # check ID Token is valid against FireBase Auth
    try:
        decoded_token = auth.verify_id_token(id_token, check_revoked=True)
    except auth.InvalidIdTokenError as ex:
        abort(
            make_response(jsonify(error="ID token is invalid, expired or revoked"), 401)
        )

    # grab the user's FireBase Auth UID
    firebase_uid = decoded_token["uid"]

    # create a User object and pass in the FireBase UID
    user = User(firebase_uid=firebase_uid)

    # try to retrieve a Xooa token for the user
    try:
        xooa_user = user.get_xooa_user()
    # if a XooaUserNotFound exception is raised then create the user in Xooa and try again to retrieve a Xooa token for the user
    except user.XooaUserNotFound:
        user.create_xooa_user()
        xooa_user = user.get_xooa_user()

    # return the user's Xooa token
    return jsonify(token=xooa_user["ApiToken"])
