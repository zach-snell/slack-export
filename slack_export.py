from slacker import Slacker
import json
import argparse
import os
import io
import shutil
import copy
from datetime import datetime
from pick import pick
from time import sleep

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
            sleep(1) # Respect the Slack API rate limit
        else:
            break

    messages.sort(key = lambda message: message['ts'])

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

    # if there's no data to write to the file, return
    if not messages:
        return

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
            outFileName = u'{room}/{file}.json'.format( room = roomDir, file = currentFileDate )
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
    outFileName = u'{room}/{file}.json'.format( room = roomDir, file = currentFileDate )
    writeMessageFile( outFileName, currentMessages )

def filterConversationsByName(channelsOrGroups, channelOrGroupNames):
    return [conversation for conversation in channelsOrGroups if conversation['name'] in channelOrGroupNames]

def promptForPublicChannels(channels):
    channelNames = [channel['name'] for channel in channels]
    selectedChannels = pick(channelNames, 'Select the Public Channels you want to export:', multi_select=True)
    return [channels[index] for channelName, index in selectedChannels]

# fetch and write history for all public channels
def fetchPublicChannels(channels):
    if dryRun:
        print("Public Channels selected for export:")
        for channel in channels:
            print(channel['name'])
        print()
        return

    for channel in channels:
        channelDir = channel['name'].encode('utf-8')
        print(u"Fetching history for Public Channel: {0}".format(channelDir))
        channelDir = channel['name'].encode('utf-8')
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

def filterDirectMessagesByUserNameOrId(dms, userNamesOrIds):
    userIds = [userIdsByName.get(userNameOrId, userNameOrId) for userNameOrId in userNamesOrIds]
    return [dm for dm in dms if dm['user'] in userIds]

def promptForDirectMessages(dms):
    dmNames = [userNamesById.get(dm['user'], dm['user'] + " (name unknown)") for dm in dms]
    selectedDms = pick(dmNames, 'Select the 1:1 DMs you want to export:', multi_select=True)
    return [dms[index] for dmName, index in selectedDms]

# fetch and write history for all direct message conversations
# also known as IMs in the slack API.
def fetchDirectMessages(dms):
    if dryRun:
        print("1:1 DMs selected for export:")
        for dm in dms:
            print(userNamesById.get(dm['user'], dm['user'] + " (name unknown)"))
        print()
        return

    for dm in dms:
        name = userNamesById.get(dm['user'], dm['user'] + " (name unknown)")
        print(u"Fetching 1:1 DMs with {0}".format(name))
        dmId = dm['id']
        mkdir(dmId)
        messages = getHistory(slack.im, dm['id'])
        parseMessages( dmId, messages, "im" )

def promptForGroups(groups):
    groupNames = [group['name'] for group in groups]
    selectedGroups = pick(groupNames, 'Select the Private Channels and Group DMs you want to export:', multi_select=True)
    return [groups[index] for groupName, index in selectedGroups]

# fetch and write history for specific private channel
# also known as groups in the slack API.
def fetchGroups(groups):
    if dryRun:
        print("Private Channels and Group DMs selected for export:")
        for group in groups:
            print(group['name'])
        print()
        return

    for group in groups:
        groupDir = group['name']
        mkdir(groupDir)
        messages = []
        print(u"Fetching history for Private Channel / Group DM: {0}".format(group['name']))
        messages = getHistory(slack.groups, group['id'])
        parseMessages( groupDir, messages, 'group' )

# fetch all users for the channel and return a map userId -> userName
def getUserMap():
    global userNamesById, userIdsByName
    for user in users:
        userNamesById[user['id']] = user['name']
        userIdsByName[user['name']] = user['id']

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
    print(u"Successfully authenticated for team {0} and user {1} ".format(teamName, currentUser))
    return testAuth

# Since Slacker does not Cache.. populate some reused lists
def bootstrapKeyValues():
    global users, channels, groups, dms
    users = slack.users.list().body['members']
    print(u"Found {0} Users".format(len(users)))
    sleep(1)
    
    channels = slack.channels.list().body['channels']
    print(u"Found {0} Public Channels".format(len(channels)))
    sleep(1)

    groups = slack.groups.list().body['groups']
    print(u"Found {0} Private Channels or Group DMs".format(len(groups)))
    sleep(1)

    dms = slack.im.list().body['ims']
    print(u"Found {0} 1:1 DM conversations\n".format(len(dms)))
    sleep(1)

    getUserMap()

# Returns the conversations to download based on the command-line arguments
def selectConversations(allConversations, commandLineArg, filter, prompt):
    global args
    if isinstance(commandLineArg, list) and len(commandLineArg) > 0:
        return filter(allConversations, commandLineArg)
    elif commandLineArg != None or not anyConversationsSpecified():
        if args.prompt:
            return prompt(allConversations)
        else:
            return allConversations
    else:
        return []

# Returns true if any conversations were specified on the command line
def anyConversationsSpecified():
    global args
    return args.publicChannels != None or args.groups != None or args.directMessages != None

# This method is used in order to create a empty Channel if you do not export public channels
# otherwise, the viewer will error and not show the root screen. Rather than forking the editor, I work with it.
def dumpDummyChannel():
    channelName = channels[0]['name']
    mkdir( channelName )
    fileDate = '{:%Y-%m-%d}'.format(datetime.today())
    outFileName = u'{room}/{file}.json'.format( room = channelName, file = fileDate )
    writeMessageFile(outFileName, [])

def finalize():
    os.chdir('..')
    if zipName:
        shutil.make_archive(zipName, 'zip', outputDirectory, None)
        shutil.rmtree(outputDirectory)
    exit()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Export Slack history')

    parser.add_argument('--token', required=True, help="Slack API token")
    parser.add_argument('--zip', help="Name of a zip file to output as")

    parser.add_argument(
        '--dryRun',
        action='store_true',
        default=False,
        help="List the conversations that will be exported (don't fetch/write history)")

    parser.add_argument(
        '--publicChannels',
        nargs='*',
        default=None,
        metavar='CHANNEL_NAME',
        help="Export the given Public Channels")

    parser.add_argument(
        '--groups',
        nargs='*',
        default=None,
        metavar='GROUP_NAME',
        help="Export the given Private Channels / Group DMs")

    parser.add_argument(
        '--directMessages',
        nargs='*',
        default=None,
        metavar='USER_NAME',
        help="Export 1:1 DMs with the given users")

    parser.add_argument(
        '--prompt',
        action='store_true',
        default=False,
        help="Prompt you to select the conversations to export")

    args = parser.parse_args()

    users = []    
    channels = []
    groups = []
    dms = []
    userNamesById = {}
    userIdsByName = {}

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

    selectedChannels = selectConversations(
        channels,
        args.publicChannels,
        filterConversationsByName,
        promptForPublicChannels)

    selectedGroups = selectConversations(
        groups,
        args.groups,
        filterConversationsByName,
        promptForGroups)

    selectedDms = selectConversations(
        dms,
        args.directMessages,
        filterDirectMessagesByUserNameOrId,
        promptForDirectMessages)

    if len(selectedChannels) > 0:
        fetchPublicChannels(selectedChannels)

    if len(selectedGroups) > 0:
        if len(selectedChannels) == 0:
            dumpDummyChannel()
        fetchGroups(selectedGroups)

    if len(selectedDms) > 0:
        fetchDirectMessages(selectedDms)

    finalize()
