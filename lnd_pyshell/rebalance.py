from lnd_pyshell.lnd_rest import *
from lnd_pyshell.utils import *
from lnd_pyshell.invoices import *
from rich import print

# TODO: fix me, and figure out arrays!
def queryRoute(
    src_pk, dest_pk, oid=None, lh=None, pay_amt=123, ignore_list=None, frame=False
):
    # base64.b64encode(bytes.fromhex(last_hop_pubkey)).decode()
    c = listChannels()
    c["pk64"] = c["remote_pubkey"].apply(
        lambda x: base64.urlsafe_b64encode(bytes.fromhex(x)).decode()
    )
    # outgoing_chan_id
    # last_hop_pubkey
    # Convert HEX pubkeys to to base64
    # for node in ignore_list:
    # 	ig64 = base64.b64encode(bytes.fromhex(node)).decode().replace('+','-').replace('/','_')
    # 	id_url_safe = ignore
    # 	id_percent_encoded = urllib.parse.quote(id_url_safe)
    target_url = f"/v1/graph/routes/{dest_pk}/{pay_amt}?source_pub_key={src_pk}"
    target_url += (
        f"&use_mission_control=true&fee_limit.fixed_msat=444000"
    )
    # target_url + f"&ignored_nodes="
    if lh:
        target_url + f"&last_hop_pubkey={lh}"
    if oid:
        target_url + f"&outgoing_chan_id={oid}"
    lnreq = sendGetRequest(target_url)
    if frame:
        f = lnreq["routes"][0]
        f["total_fees_msat"] = "0"
        f["total_fees"] = "0"
        return f
    hops = lnreq["routes"][0]["hops"]
    hoplist = []
    for hop in hops:
        hoplist.append(hop)
    # It only ever returns 1 route
    return lnreq["routes"][0]["hops"]


def rebalance(amt, outgoing_chan_id, last_hop_pubkey, fee_msat=4200, force=False):
    print(
        f"Rebalancing chan id: { CID2Alias(outgoing_chan_id) } --> {getAlias(last_hop_pubkey)}. "
    )
    if not force:
        accept = input(f"Press: (y/n)")
        if accept == "y":
            pass
        else:
            print("Rebalance canceled.")
            return None, 0, None
    # payreq = addInvoice(amt, "balance1")["payment_request"]
    payreq, amt = rebalanceInvoice(110000,300000)
    print(f"Retrieved Request: {payreq}")
    endpoint = "/v1/channels/transactions"
    bdata = {}
    bdata["fee_limit"] = {"fixed_msat": fee_msat}
    bdata["outgoing_chan_id"] = f"{outgoing_chan_id}"
    bdata["allow_self_payment"] = True
    bdata["last_hop_pubkey"] = base64.b64encode(bytes.fromhex(last_hop_pubkey)).decode()
    bdata["payment_request"] = payreq
    url = base_url + endpoint
    start = datetime.now()
    lnreq = requests.post(
        url, headers=headers, verify=cert_path, data=json.dumps(bdata)
    )
    end = datetime.now()
    data = lnreq.json()
    hops = pandas.DataFrame()
    if data["payment_error"] != "":
        print("payment error")
        data["payment_error"].split("\n")[0]
        print(data["payment_error"])
        # Unsuccessful so costs 0 sats
        tf = 0
    else:
        hops = pandas.DataFrame(data["payment_route"]["hops"])
        # print(hops.columns)
        hops["alias"] = hops.apply(lambda x: getAlias(x.pub_key), axis=1)
        # Get first and last hop
        chans = list(hops.iloc[[0, -1]].chan_id)
        print(f"hops and chans: {chans}")
        # This is the printout we want to see
        print(
            hops[
                [
                    "alias",
                    "chan_id",
                    "chan_capacity",
                    "expiry",
                    "amt_to_forward_msat",
                    "fee_msat",
                    "pub_key",
                ]
            ]
        )
        print(listChannels().query("chan_id.isin(@chans)"))
        # print(hops.dtypes)
        # print(hops.columns)
        tf = int(data["payment_route"]["total_fees_msat"]) / 1000
    dur = (end - start).total_seconds()
    print(f"Total Routing Fees: {tf}")
    print(f"Payment Duration: {dur}")
    return tf, dur, lnreq, hops


def rebalance_alg():
    cycles = 0
    total_routing_fees = 0
    while cycles < 10:
        # Depleted channels
        depleted = listChannels().query(
            "balanced < 0.3 and active == True and capacity > 3000000"
        )
        num_depleted = depleted.shape[0]
        # Full channels
        glut = listChannels().query(
            "balanced > 0.65 and active == True and capacity > 3000000"
        )
        num_glut = glut.shape[0]
        print(f"{num_glut} glut--> {num_depleted} depleted")
        source = glut.sample(1)
        dest = depleted.sample(1)
        print(f"{source.alias.item()} ---> {dest.alias.item()} ")
        # rebalance between 100K and 250K sats
        rebalance_amt = random.randint(100,250) * 1000
        a, b, c, d = rebalance(
            rebalance_amt, source.chan_id.item(), dest.remote_pubkey.item(), 8000, force=True
        )
        total_routing_fees += a
        error = c.json()["payment_error"]
        print(f"Payment Response: {error}")
        print(f"Total Routing Fees: {total_routing_fees}")
        if error == "":
            cycles += 1
            print("Successful route")
            looper = 0
            while error == "":
                a, b, c, d = rebalance(
                    100000,
                    source.chan_id.item(),
                    dest.remote_pubkey.item(),
                    8000,
                    force=True,
                )
                error = c.json()["payment_error"]
                total_routing_fees += a
                looper += 1
                if looper == 3:
                    break

def rebe():
    # Source sats
    source = listChannels().query("balanced >= 0.666").sort_values(by="local_balance")
    # dry channels
    dry = listChannels().query("balanced <= 0.5").sort_values(by="local_balance")
    print(f"Count: Source: {source.shape[0]} --> Dry: {dry.shape[0]}")
    s = source.sample().chan_id.item()
    d = dry.sample().remote_pubkey.item()
    amt = 250000
    print(f"Rebalance: {CID2Alias(s)} ---> {getAlias(d)}")
    return rebalance(amt, s, d, 6000, True)


if __name__ == "__main__":
    from time import sleep

    listChannels().sort_values(by="capacity")

    source = (
        listChannels()
        .query("balanced >= 0.80 ")
        .query("active == True")
        .sort_values(by="local_balance")
    )
    dry = (
        listChannels()
        .query("balanced >= 0.1 & balanced <= 0.6")
        .query("active == True")
        .sort_values(by="local_balance")
    )

    ## **********************************
    # Invert channel balances
    ## **********************************

    rebalance_amt = 200000
    max_fee_sats = 7000
    for lh in dry.remote_pubkey:
        for cid in source.chan_id:
            result = rebalance(rebalance_amt, cid, lh, max_fee_sats, True)
            sleep(2)
            error_msg = result[2].json()["payment_error"]
            print(f"Error Message: {error_msg}")
            # no_route is worst result, usually wont fix itself
            if error_msg == "no_route":
                break
            print("Retrying pair until failure")
            retry = 0
            # Found routes, hops frame is is not empty
            while not result[3].empty:
                print(f"Successfully sent {retry} times!")
                result = rebalance(rebalance_amt, cid, lh, max_fee_sats, True)
                retry += 1
                print(result)
                sleep(2)

    ## **********************************
    # Rebalance a single depleted channel
    ## **********************************

    source = (
        listChannels()
        .query("balanced >= 0.5")
        .query("active == True")
        .sort_values(by="local_balance")
    )
    target_lh = "03037dc08e9ac63b82581f79b662a4d0ceca8a8ca162b1af3551595b8f2d97b70a"
    rebalance_amt = 200000
    max_fee_sats = 15000
    for cid in source.chan_id:
        result = rebalance(rebalance_amt, cid, target_lh, max_fee_sats, True)
        sleep(2)
        error_msg = result[2].json()["payment_error"]
        print(f"Error Message: {error_msg}")
        # no_route is worst result, usually wont fix itself
        if error_msg == "no_route":
            continue
        print("Retrying pair until failure")
        retry = 0
        # Found routes, hops frame is is not empty
        while error_msg != "no_route":
            print(f"Successfully sent {retry} times!")
            result = rebalance(rebalance_amt, cid, target_lh, max_fee_sats, True)
            error_msg = result[2].json()["payment_error"]
            retry += 1
            if retry > 25:
                break
            print(result)
            sleep(2)

        ## **********************************
        #
        ## **********************************

        a = getForwards()
        dry = list(a.tail(200).chan_id_out.unique())
        source = list(a.tail(200).chan_id_in.unique())

        dry = listChannels().query("chan_id.isin(@dry)").query("balanced < 0.4")
        source = listChannels().query("chan_id.isin(@source)").query("balanced > 0.6")

        pandas.concat([adry, asrc], ignore_index=True).drop_duplicates().reset_index(
            drop=True
        )

        from time import sleep

        fee_total = 0
        while True:
            fees, duration, r, hops = rebe()
            fee_total += fees
            print(f"Total Fees: {fee_total}")
            sleep(10)

        # get fees for channels
        c = listChannels()
        mypk = getMyPK()

        d = getChanPolicy("693792936758935553")

        d.query(f"pubkey != '{mypk}' ")[
            ["time_lock_delta", "min_htlc", "fee_base_msat"]
        ]

        c.chan_id.apply(
            lambda x: g.update(
                {
                    x: getChanPolicy(x).query(f"pubkey != '{mypk}' ")[
                        ["time_lock_delta", "min_htlc", "fee_base_msat"]
                    ]
                }
            )
        )
