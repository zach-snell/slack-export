from slacker import Slacker
import json
import argparse
import os
import io
import shutil
import copy
from datetime import datetime

# fetches the complete message history for a channel/group/im
#
# pageableObject could be:
# slack.channel
# slack.groups
# slack.im
#
# channelId is the id of the channel/group/im you want to download history for.
def getHistory(pageableObject, channelId, pageSize = 100):
    messages = []
    lastTimestamp = None

    while(True):
        response = pageableObject.history(
            channel = channelId,
            latest    = lastTimestamp,
            oldest    = 0,
            count     = pageSize
        ).body

        messages.extend(response['messages'])

        if (response['has_more'] == True):
            lastTimestamp = messages[-1]['ts'] # -1 means last element in a list
        else:
            break
    return messages


def mkdir(directory):
    if not os.path.isdir(directory):
        os.makedirs(directory)


# create datetime object from slack timestamp ('ts') string
def parseTimeStamp( timeStamp ):
    if '.' in timeStamp:
        t_list = timeStamp.split('.')
        if len( t_list ) != 2:
            raise ValueError( 'Invalid time stamp' )
        else:
            return datetime.utcfromtimestamp( float(t_list[0]) )


# move channel files from old directory to one with new channel name
def channelRename( oldRoomName, newRoomName ):
    # check if any files need to be moved
    if not os.path.isdir( oldRoomName ):
        return
    mkdir( newRoomName )
    for fileName in os.listdir( oldRoomName ):
        shutil.move( os.path.join( oldRoomName, fileName ), newRoomName )
    os.rmdir( oldRoomName )


def writeMessageFile( fileName, messages ):
    directory = os.path.dirname(fileName)

    if not os.path.isdir( directory ):
        mkdir( directory )

    with open(fileName, 'w') as outFile:
        json.dump( messages, outFile, indent=4)


# parse messages by date
def parseMessages( roomDir, messages, roomType ):
    nameChangeFlag = roomType + "_name"

    currentFileDate = ''
    currentMessages = []
    for message in messages:
        #first store the date of the next message
        ts = parseTimeStamp( message['ts'] )
        fileDate = '{:%Y-%m-%d}'.format(ts)

        #if it's on a different day, write out the previous day's messages
        if fileDate != currentFileDate:
            outFileName = '{room}/{file}.json'.format( room = roomDir, file = currentFileDate )
            writeMessageFile( outFileName, currentMessages )
            currentFileDate = fileDate
            currentMessages = []

        # check if current message is a name change
        # dms won't have name change events
        if roomType != "im" and ( 'subtype' in message ) and message['subtype'] == nameChangeFlag:
            roomDir = message['name']
            oldRoomPath = message['old_name']
            newRoomPath = roomDir
            channelRename( oldRoomPath, newRoomPath )

        currentMessages.append( message )
    outFileName = '{room}/{file}.json'.format( room = roomDir, file = currentFileDate )
    writeMessageFile( outFileName, currentMessages )


# fetch and write history for all public channels
def getChannels():
    print("Obtaining Channel Histories: ")
    if dryRun:
        for channel in channels:
            print(channel['name'].encode("utf-8"))
        return
    for channel in channels:
        print("getting history for channel {0}".format(channel['name']))
        channelDir = channel['name']
        mkdir( channelDir )
        messages = getHistory(slack.channels, channel['id'])
        parseMessages( channelDir, messages, 'channel')

# write channels.json file
def dumpChannelFile():
    print("Making channels file")

    private = []
    mpim = []

    for group in groups:
        if group['is_mpim']:
            mpim.append(group)
            continue
        private.append(group)
    
    # slack viewer wants DMs to have a members list, not sure why but doing as they expect
    for dm in dms:
        dm['members'] = [dm['user'], tokenOwnerId]

    #We will be overwriting this file on each run.
    with open('channels.json', 'w') as outFile:
        json.dump( channels , outFile, indent=4)
    with open('groups.json', 'w') as outFile:
        json.dump( private , outFile, indent=4)
    with open('mpims.json', 'w') as outFile:
        json.dump( mpim , outFile, indent=4)
    with open('dms.json', 'w') as outFile:
        json.dump( dms , outFile, indent=4)


# fetch and write history for all direct message conversations
# also known as IMs in the slack API.
def getDirectMessages():
    print("Found direct messages (1:1) with the following users:")

    if dryRun:
        for dm in dms:
            print(userIdNameMap.get(dm['user'], dm['user'] + " (name unknown)"))
        return
    for dm in dms:
        name = userIdNameMap.get(dm['user'], dm['user'] + " (name unknown)")
        print("getting history for direct messages with {0}".format(name))
        dmId = dm['id']
        mkdir(dmId)
        messages = getHistory(slack.im, dm['id'])
        parseMessages( dmId, messages, "im" )
        return
        
# fetch and write history for specific private channel
# also known as groups in the slack API.
def getPrivateChannels(channelNames = []):
    augmentedGroups = groups
    if len(channelNames) != 0:
        augmentedGroups = [x for x in augmentedGroups if x['name'] in channelNames]
    
    print("Getting history for Private Channels and Group Messages")

    if dryRun:
        for group in augmentedGroups:
            print("{0}: ({1} members)".format(group['name'], len(group['members'])))
        return

    for group in augmentedGroups:
        groupDir = group['name']
        mkdir(groupDir)
        messages = []
        print("getting history for private channel {0} with id {1}".format(group['name'], group['id']))
        messages = getHistory(slack.groups, group['id'])
        parseMessages( groupDir, messages, 'group' )

# fetch all users for the channel and return a map userId -> userName
def getUserMap():
    global userIdNameMap
    for user in users:
        userIdNameMap[user['id']] = user['name']

# stores json of user info
def dumpUserFile():
    #write to user file, any existing file needs to be overwritten.
    with open( "users.json", 'w') as userFile:
        json.dump( users, userFile, indent=4 )

# get basic info about the slack channel to ensure the authentication token works
def doTestAuth():
    testAuth = slack.auth.test().body
    teamName = testAuth['team']
    currentUser = testAuth['user']
    print("Successfully authenticated for team {0} and user {1} ".format(teamName, currentUser))
    return testAuth

# Since Slacker does not Cache.. populate some reused lists
def bootstrapKeyValues():
    global users, channels, groups, dms
    users = slack.users.list().body['members']
    print("found {0} users ".format(len(users)))
    
    channels = slack.channels.list().body['channels']
    print("found {0} channels ".format(len(channels)))

    groups = slack.groups.list().body['groups']
    print("found {0} private channels or group messages".format(len(groups)))

    dms = slack.im.list().body['ims']
    print("found {0} unique user direct messages".format(len(dms)))

    getUserMap()

# This method is used in order to create a empty Channel if you do not export anything but private channels
# otherwise, the viewer will error and not show the root screen. Rather than forking the editor, I work with it.
def dumpDummyChannel():
    channelName = channels[0]['name']
    mkdir( channelName )
    fileDate = '{:%Y-%m-%d}'.format(datetime.today())
    outFileName = '{room}/{file}.json'.format( room = channelName, file = fileDate )
    writeMessageFile(outFileName, [])

def finalize():
    os.chdir('..')
    if zipName:
        shutil.make_archive(zipName, 'zip', outputDirectory, None)
        shutil.rmtree(outputDirectory)
    exit()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='download slack history')

    parser.add_argument('--token', help="an api token for a slack user")
    parser.add_argument('--zip', help="name of a zip file to output as")

    parser.add_argument(
        '--dryRun',
        action='store_true',
        default=False,
        help="if dryRun is true, don't fetch/write history only get channel names")

    parser.add_argument(
        '--onlySpecifiedPrivateChannels',
		default=[],
        nargs='*',
        help="only fetch the specified private channels or group messages")

    parser.add_argument(
        '--skipPrivateChannels',
        action='store_true',
        default=False,
        help="skip fetching history for private channels, includes group messages.")

    parser.add_argument(
        '--skipChannels',
        action='store_true',
        default=False,
        help="skip fetching history for channels")

    parser.add_argument(
        '--skipDirectMessages',
        action='store_true',
        default=False,
        help="skip fetching history for directMessages")

    args = parser.parse_args()

    users = []    
    channels = []
    groups = []
    dms = []
    userIdNameMap = {}

    slack = Slacker(args.token)
    testAuth = doTestAuth()
    tokenOwnerId = testAuth['user_id']

    bootstrapKeyValues()

    dryRun = args.dryRun
    zipName = args.zip

    outputDirectory = "{0}-slack_export".format(datetime.today().strftime("%Y%m%d-%H%M%S"))
    mkdir(outputDirectory)
    os.chdir(outputDirectory)

    if not dryRun:
        dumpUserFile()
        dumpChannelFile()

    if args.onlySpecifiedPrivateChannels:
        dumpDummyChannel()
        getPrivateChannels(args.onlySpecifiedPrivateChannels)
        finalize()

    if not args.skipChannels:
        getChannels()

    if not args.skipPrivateChannels:
        getPrivateChannels()

    if not args.skipDirectMessages:
        getDirectMessages()
    finalize()
